"""程序化生成游戏音频（纯标准库，零第三方依赖）。

用法：
    python tools/gen_audio.py              # 生成全部音频
    python tools/gen_audio.py bgm_battle   # 只生成指定目标

输出目录默认 assets/audio/（可用 --out 覆盖）。生成的都是 22050Hz 16-bit
WAV，pygame-ce 的 SDL_mixer 可直接加载。波形合成采用查表振荡器 + 事件序列，
全程确定性（固定种子），可反复重建。

音高约定：midi 0=C-1（440Hz 对应 A4=69）。
"""

from __future__ import annotations

import argparse
import math
import sys
import wave
from array import array
from pathlib import Path

SR = 22050  # 采样率
SEED = 20260908  # 确定性种子
TABLEN = 256  # 波表长度（越大越接近理想波形）

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "assets" / "audio"


# ---------------- 音高 / 波形 ----------------

def freq(midi: float) -> float:
    """MIDI 音高 -> 频率 Hz。"""
    return 440.0 * (2.0 ** ((midi - 69.0) / 12.0))


def _tables() -> dict[str, array]:
    """构造各波形的 256 点查表。"""
    out: dict[str, array] = {}
    for kind in ("sine", "square", "tri", "saw", "pw25"):
        t = array("f", [0.0]) * TABLEN
        for i in range(TABLEN):
            x = i / TABLEN
            if kind == "sine":
                v = math.sin(2.0 * math.pi * x)
            elif kind == "square":
                v = 1.0 if x < 0.5 else -1.0
            elif kind == "pw25":
                v = 1.0 if x < 0.25 else -1.0
            elif kind == "tri":
                v = 1.0 - 4.0 * abs(x - 0.5)  # -1..1 三角波
            else:  # saw
                v = 2.0 * x - 1.0
            t[i] = v
        out[kind] = t
    return out


_TABLES = _tables()


# ---------------- 混音缓冲 ----------------

class Mix:
    """立体声 float 缓冲 + 事件渲染。

    add():   有确定音高的振荡器音符（支持扫频、AD 包络、等功率声像）。
    noise(): 白噪声突发（LCG 伪随机，避免 random() 调用开销）。
    """

    __slots__ = ("L", "R", "n", "_ns")

    def __init__(self, seconds: float) -> None:
        self.n = int(seconds * SR) + 2
        self.L = array("f", [0.0]) * self.n
        self.R = array("f", [0.0]) * self.n
        self._ns = SEED & 0x7FFFFFFF  # 噪声 LCG 状态

    # 采样总数 = dur_s * SR，转成整数偏移
    def add(
        self,
        start_s: float,
        dur_s: float,
        midi0: float,
        midi1: float | None = None,
        wave_kind: str = "sine",
        amp: float = 0.2,
        pan: float = 0.5,
        mode: str = "pluck",  # "pluck"=指数衰减 | "sustain"=持续后短释放
        tau: float = 0.12,
        attack: float = 0.004,
        release: float = 0.05,
    ) -> None:
        """midi0(->midi1) 音高。"""
        self._sweep(start_s, dur_s, freq(midi0), freq(midi1 if midi1 is not None else midi0),
                    wave_kind, amp, pan, mode, tau, attack, release)

    def add_hz(
        self,
        start_s: float,
        dur_s: float,
        f0: float,
        f1: float | None = None,
        wave_kind: str = "sine",
        amp: float = 0.2,
        pan: float = 0.5,
        mode: str = "pluck",
        tau: float = 0.12,
        attack: float = 0.004,
        release: float = 0.05,
    ) -> None:
        """f0(->f1) 直接给 Hz（底鼓/扫频用）。"""
        self._sweep(start_s, dur_s, f0, f1 if f1 is not None else f0,
                    wave_kind, amp, pan, mode, tau, attack, release)

    def _sweep(self, start_s, dur_s, f0h, f1h, wave_kind, amp, pan,
               mode, tau, attack, release) -> None:
        s0 = max(0, int(start_s * SR))
        s1 = min(self.n, s0 + int(dur_s * SR) + 1)
        if s0 >= s1:
            return
        tb = _TABLES[wave_kind]
        k = TABLEN / SR
        gl = math.sqrt(max(0.0, 1.0 - pan)) * amp
        gr = math.sqrt(max(0.0, pan)) * amp
        L, R = self.L, self.R
        if mode == "sustain":
            a = max(1e-4, attack)
            rl = max(0.004, release)
            pos = 0.0
            for i in range(s0, s1):
                t = (i - s0) / SR
                f = f0h + (f1h - f0h) * (t / max(1e-6, dur_s))
                pos += f * k
                p = pos
                q = int(p)
                idx = q & (TABLEN - 1)
                jdx = (idx + 1) & (TABLEN - 1)
                fr = p - float(q)
                s = tb[idx] + (tb[jdx] - tb[idx]) * fr
                g = min(1.0, t / a)
                if t > dur_s - rl:
                    g = min(g, max(0.0, (dur_s - t) / rl))
                v = s * g
                L[i] += v * gl
                R[i] += v * gr
        else:  # pluck / perc
            a = max(1e-4, attack)
            ta = max(1e-4, tau)
            dur = max(1e-6, dur_s)
            pos = 0.0
            for i in range(s0, s1):
                t = (i - s0) / SR
                f = f0h + (f1h - f0h) * (t / dur)
                pos += f * k
                p = pos
                q = int(p)
                idx = q & (TABLEN - 1)
                jdx = (idx + 1) & (TABLEN - 1)
                fr = p - float(q)
                s = tb[idx] + (tb[jdx] - tb[idx]) * fr
                g = math.exp(-t / ta) * min(1.0, t / a)
                v = s * g
                L[i] += v * gl
                R[i] += v * gr

    def noise(
        self,
        start_s: float,
        dur_s: float,
        amp: float = 0.2,
        pan: float = 0.5,
        tau: float = 0.05,
    ) -> None:
        s0 = max(0, int(start_s * SR))
        s1 = min(self.n, s0 + int(dur_s * SR) + 1)
        if s0 >= s1:
            return
        gl = math.sqrt(max(0.0, 1.0 - pan)) * amp
        gr = math.sqrt(max(0.0, pan)) * amp
        L, R = self.L, self.R
        s = self._ns
        ta = max(1e-4, tau)
        for i in range(s0, s1):
            t = (i - s0) / SR
            s = (s * 1103515245 + 12345) & 0x7FFFFFFF
            v = (s / 0x3FFFFFFF - 1.0) * math.exp(-t / ta)
            L[i] += v * gl
            R[i] += v * gr
        self._ns = s

    def peak(self) -> float:
        m = 0.0
        for arr in (self.L, self.R):
            for v in arr:
                a = -v if v < 0 else v
                if a > m:
                    m = a
        return m

    def save(self, path: Path, target: float = 0.86) -> None:
        """归一化后写 16-bit 立体声 WAV。"""
        pk = self.peak()
        scale = (target / pk) if pk > 0 else 0.0
        path.parent.mkdir(parents=True, exist_ok=True)
        n = self.n
        data = array("h")
        L, R = self.L, self.R
        sc = 32767.0 * scale
        for i in range(n):
            lv = int(L[i] * sc)
            rv = int(R[i] * sc)
            if lv > 32767:
                lv = 32767
            elif lv < -32768:
                lv = -32768
            if rv > 32767:
                rv = 32767
            elif rv < -32768:
                rv = -32768
            data.append(lv)
            data.append(rv)
        if sys.byteorder == "big":
            data.byteswap()
        with wave.open(str(path), "wb") as wf:
            wf.setnchannels(2)
            wf.setsampwidth(2)
            wf.setframerate(SR)
            wf.writeframes(data.tobytes())


def _fade_edges(m: Mix, ms: float = 10.0) -> None:
    """首尾做 8~10ms 淡入淡出，保证无缝循环时无爆音。"""
    n = int(ms / 1000.0 * SR)
    n = min(n, m.n // 2)
    for i in range(n):
        g = i / n
        for arr in (m.L, m.R):
            arr[i] *= g
            arr[m.n - 1 - i] *= g


# ---------------- 组合子 ----------------

def _bar_arp(m: Mix, start_s: float, bar_s: float, pad: list[int], amp: float,
             base: int, wave_kind: str = "tri", pan: float = 0.5) -> None:
    """一小节内把 pad 音 +12 后做 8 分音符上下行琶音。"""
    n8 = int(round(bar_s / 0.5))  # 一小节近似 8 分音符数（bpm 快慢自适配）
    n8 = max(4, min(16, n8))
    step = bar_s / n8
    up = True
    p = 0
    for j in range(n8):
        idx = p % 3
        note = pad[idx] + base + (24 if j % 8 == 7 else 12)
        pan_j = pan + 0.12 * (0.5 if j % 2 else -0.5)
        m.add(start_s + j * step, step * 0.92, note, amp=amp, pan=pan_j)
        if up:
            p += 1
            if p % 3 == 0:
                up = False
        else:
            p -= 1
            if p <= 0:
                up = True
                p = 0


# ---------------- 各 BGM ----------------

def build_deploy() -> Mix:
    """运营/布阵：约 96BPM * 8 小节 ≈ 20s 舒缓循环。

    进行 | Am F C G | x2，柔和 pad + 三角波琶音 + 方波低音 + 稀疏高音动机。
    """
    bpm = 96.0
    beat = 60.0 / bpm
    bar_s = beat * 4.0
    bars = [
        (45, [57, 60, 64]),  # Am
        (41, [57, 60, 65]),  # F
        (48, [55, 60, 64]),  # C
        (43, [59, 62, 67]),  # G
    ] * 2
    total = bar_s * len(bars)
    m = Mix(total + 0.3)

    for bi, (bass, pad) in enumerate(bars):
        t0 = bi * bar_s
        # pad：长音 + 一点 detune 般的第二振荡器（三角低八度）
        for ni, note in enumerate(pad):
            m.add(t0, bar_s, note, wave_kind="sine", amp=0.05, mode="sustain",
                  pan=0.4 + 0.1 * ni, release=0.12)
            m.add(t0, bar_s, note - 12, wave_kind="tri", amp=0.022, mode="sustain",
                  pan=0.45 + 0.1 * ni, release=0.12)
        # 低音：2、3 拍方波短促拨奏（第 1 拍让给 pad）
        m.add(t0 + beat * 2, beat * 0.6, bass, wave_kind="square", amp=0.10, tau=0.1)
        m.add(t0 + beat * 3, beat * 0.6, bass, wave_kind="square", amp=0.10, tau=0.1)
        # 琶音（左右摇摆）
        _bar_arp(m, t0, bar_s, pad, amp=0.075, base=0, wave_kind="tri")
        # 稀疏高音动机：隔小节出现两音（长音 + 短音），音高取自和弦音
        if bi % 2 == 1:
            hi = [pad[1] + 24, pad[0] + 36, pad[2] + 24]
            k = (bi // 2) % 3
            m.add(t0 + beat * 0.5, beat * 1.6, hi[k], wave_kind="sine", amp=0.06, tau=0.45)
            m.add(t0 + beat * 2.75, beat * 0.5, pad[(k + 1) % 3] + 24,
                  wave_kind="sine", amp=0.045, tau=0.18)
        # 轻 shaker：每拍后半拍极轻噪声
        for bj in range(4):
            m.noise(t0 + beat * (bj + 0.5), 0.03, amp=0.008, pan=0.4 + 0.2 * (bj % 2))

    _fade_edges(m)
    return m


def build_battle() -> Mix:
    """开战：约 132BPM * 16 小节 ≈ 29s 强节奏循环。

    进行 | Em C G D | x4，四踩底鼓 + 军鼓 + 闭合镲 + 八分方波低音 +
    16 分高频琶音 + 每 4 小节和弦乐句。
    """
    bpm = 132.0
    beat = 60.0 / bpm
    bar_s = beat * 4.0
    bars = [
        (40, [52, 55, 59]),  # Em
        (36, [48, 52, 55]),  # C
        (43, [55, 59, 62]),  # G
        (38, [50, 54, 57]),  # D
    ] * 4
    total = bar_s * len(bars)
    m = Mix(total + 0.3)

    for bi, (bass, pad) in enumerate(bars):
        t0 = bi * bar_s
        # 底鼓：每拍（150->42Hz 短促扫频）
        for bj in range(4):
            m.add_hz(t0 + bj * beat, 0.16, 150, 42, wave_kind="sine", amp=0.55, tau=0.07)
        # 军鼓：第 2、4 拍
        for bj in (1, 3):
            ts = t0 + bj * beat
            m.noise(ts, 0.12, amp=0.20, pan=0.5, tau=0.06)
            m.add(ts, 0.08, 196, wave_kind="tri", amp=0.16, tau=0.04)
        # 闭合镲：8 分音符，反拍重一点
        for bj in range(8):
            ts = t0 + bj * beat / 2
            m.noise(ts, 0.05, amp=0.10 if bj % 2 else 0.055, pan=0.5, tau=0.028)
        # 低音：方波八分推动（根音 + 高八度交替）
        for bj in range(8):
            ts = t0 + bj * beat / 2
            note = bass if bj % 2 == 0 else bass + 12
            m.add(ts, beat / 2 * 0.72, note, wave_kind="square", amp=0.085, tau=0.09)
        # 高频琶音：16 分音符 chord-tone 上下行（比低频琶音轻）
        step = beat / 4
        n16 = 16
        idx_seq = [0, 1, 2, 1, 2, 0, 1, 2, 0, 2, 1, 0, 2, 1, 0, 2]
        for j in range(n16):
            note = pad[idx_seq[j]] + 24
            m.add(t0 + j * step, step * 0.9, note, wave_kind="tri", amp=0.05, pan=0.5)
        # 每 4 小节（bi%4==3）加一段乐句音：高音方波，两拍上行
        if bi % 4 == 3:
            notes = [pad[0] + 24, pad[1] + 24, pad[2] + 24, pad[2] + 36]
            for j, nt in enumerate(notes):
                m.add(t0 + beat * j, beat * 0.75, nt, wave_kind="square", amp=0.075, tau=0.14)
            m.add(t0 + beat * 4 - 0.05, 0.2, pad[2] + 36, wave_kind="sine", amp=0.06, tau=0.1)

    _fade_edges(m)
    return m


def build_victory() -> Mix:
    """胜利小段：120BPM 两小节上行号角 + 收束和弦，≈3.5s。"""
    bpm = 120.0
    beat = 60.0 / bpm
    total = beat * 8 + 0.2
    m = Mix(total)
    # 上行号角 C5 E5 G5 C6（方波，模拟 synth 号角）
    run = [72, 76, 79, 84]
    for j, nt in enumerate(run):
        m.add(j * beat, beat * 0.9, nt, wave_kind="square", amp=0.13, tau=0.3)
        m.noise(j * beat + beat * 0.02, 0.03, amp=0.02)
    # 收束和弦 C 大调（sine + 一点方波高音）
    chord = [60, 64, 67, 72]
    ts = 4 * beat
    for k, nt in enumerate(chord):
        m.add(ts, beat * 3.6, nt, wave_kind="sine", amp=0.075, mode="sustain", release=0.15)
    m.add(ts + 0.05, beat * 3.6, 84, wave_kind="square", amp=0.05, mode="sustain", release=0.2)
    # 收尾小鼓点
    for j in range(3):
        m.noise((5 + j) * beat, 0.09, amp=0.08, tau=0.05)
    return m


def build_defeat() -> Mix:
    """失败小段：90BPM 缓慢下行小调（Am），≈3.2s。"""
    bpm = 90.0
    beat = 60.0 / bpm
    total = beat * 6 + 0.2
    m = Mix(total)
    # 下行叹息动机：A4 E4 C4 A3（三角 + sine 双振荡）
    seq = [69, 64, 60, 57]
    for j, nt in enumerate(seq):
        ts = j * beat * 1.2
        m.add(ts, beat * 1.4, nt, wave_kind="tri", amp=0.10, tau=0.9)
        m.add(ts, beat * 1.4, nt - 12, wave_kind="sine", amp=0.08, tau=0.8)
    # 低音 Am：A2 长音衬底
    m.add(0, beat * 6, 45, wave_kind="sine", amp=0.09, mode="sustain", release=0.2)
    m.add(0.1, beat * 6, 45 - 12, wave_kind="tri", amp=0.03, mode="sustain", release=0.2)
    return m


# ---------------- UI 音效 ----------------

def build_sfx_buy() -> Mix:
    """购买：上行两声"金币"（B5 -> E6 方波）。"""
    m = Mix(0.5)
    m.add(0.0, 0.09, 83, wave_kind="square", amp=0.13, tau=0.06)
    m.add(0.09, 0.24, 88, wave_kind="square", amp=0.16, tau=0.13)
    m.add(0.09, 0.24, 88, wave_kind="sine", amp=0.08, tau=0.13)
    return m


def build_sfx_sell() -> Mix:
    """卖出：下行两声（E6 -> B5 -> G5）。"""
    m = Mix(0.5)
    m.add(0.0, 0.07, 88, wave_kind="square", amp=0.13, tau=0.05)
    m.add(0.07, 0.10, 83, wave_kind="square", amp=0.11, tau=0.06)
    m.add(0.17, 0.20, 79, wave_kind="square", amp=0.12, tau=0.09)
    m.add(0.17, 0.20, 79, wave_kind="sine", amp=0.07, tau=0.09)
    return m


def build_sfx_refresh() -> Mix:
    """刷新：快速噪声"唰"声（短促）。"""
    m = Mix(0.4)
    m.noise(0.0, 0.16, amp=0.30, pan=0.5, tau=0.05)
    m.add_hz(0.0, 0.05, 900, 500, wave_kind="tri", amp=0.06, tau=0.04)
    return m


def build_sfx_lock() -> Mix:
    """锁定/解锁：低频"咔哒"双短音。"""
    m = Mix(0.4)
    m.add(0.0, 0.09, 210, 150, wave_kind="square", amp=0.20, tau=0.05)
    m.noise(0.0, 0.03, amp=0.10)
    m.add(0.12, 0.09, 180, 130, wave_kind="square", amp=0.16, tau=0.05)
    return m


def build_sfx_equip() -> Mix:
    """穿装备：轻柔"叮"（G5 sine）。"""
    m = Mix(0.3)
    m.add(0.0, 0.16, 91, wave_kind="sine", amp=0.22, tau=0.08)
    m.add(0.0, 0.16, 91 + 12, wave_kind="sine", amp=0.06, tau=0.06)
    return m


def build_sfx_combine() -> Mix:
    """装备合成：四连上行 sparkle（C6 E6 G6 C7）。"""
    m = Mix(0.5)
    seq = [84, 88, 91, 96]
    for j, nt in enumerate(seq):
        ts = j * 0.06
        m.add(ts, 0.16, nt, wave_kind="square", amp=0.10, tau=0.07)
        m.add(ts, 0.16, nt + 12, wave_kind="sine", amp=0.05, tau=0.06)
    m.noise(0.0, 0.14, amp=0.06, tau=0.04)
    return m


def build_sfx_star() -> Mix:
    """升星/升级：五音上行号角 + 收束（C6 D6 E6 G6 C7）。"""
    m = Mix(0.8)
    seq = [84, 86, 88, 91, 96]
    for j, nt in enumerate(seq):
        m.add(j * 0.07, 0.26, nt, wave_kind="square", amp=0.11, tau=0.12)
        m.add(j * 0.07, 0.26, nt + 12, wave_kind="sine", amp=0.05, tau=0.10)
    ts = 5 * 0.07
    for k, nt in enumerate([84, 88, 91, 96]):
        m.add(ts, 0.4, nt, wave_kind="sine", amp=0.06, mode="sustain", release=0.2)
    return m


def build_sfx_fight() -> Mix:
    """开战：低频"咚" + 噪声轰鸣（短促有力）。"""
    m = Mix(0.6)
    m.add_hz(0.0, 0.14, 140, 44, wave_kind="sine", amp=0.55, tau=0.06)
    m.noise(0.0, 0.30, amp=0.16, pan=0.5, tau=0.10)
    m.add_hz(0.05, 0.22, 65, 90, wave_kind="saw", amp=0.05, tau=0.1)
    return m


def build_sfx_error() -> Mix:
    """无效操作：低沉双"嘟"（金不足/不可合成等）。"""
    m = Mix(0.5)
    m.add(0.0, 0.14, 76, wave_kind="square", amp=0.12, tau=0.09)
    m.add(0.16, 0.2, 71, wave_kind="square", amp=0.12, tau=0.11)
    return m


# ---------------- 构建器 ----------------

def build_all() -> dict[str, Mix]:
    builders = {
        "bgm_deploy": build_deploy,
        "bgm_battle": build_battle,
        "bgm_victory": build_victory,
        "bgm_defeat": build_defeat,
        "sfx_buy": build_sfx_buy,
        "sfx_sell": build_sfx_sell,
        "sfx_refresh": build_sfx_refresh,
        "sfx_lock": build_sfx_lock,
        "sfx_equip": build_sfx_equip,
        "sfx_combine": build_sfx_combine,
        "sfx_star": build_sfx_star,
        "sfx_fight": build_sfx_fight,
        "sfx_error": build_sfx_error,
    }
    return {k: fn() for k, fn in builders.items()}


def _check(path: Path) -> None:
    with wave.open(str(path), "rb") as wf:
        ch = wf.getnchannels()
        rate = wf.getframerate()
        n = wf.getnframes()
    print(f"  OK  {path.name:<14} {ch}ch {rate}Hz {n / rate:.2f}s  {path.stat().st_size / 1024:.0f}KB")


def main() -> None:
    ap = argparse.ArgumentParser(description="生成游戏 BGM / UI 音效 WAV")
    ap.add_argument("targets", nargs="*", help="留空生成全部；可指定如 bgm_battle sfx_buy")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="输出目录")
    ap.add_argument("--check", action="store_true", help="生成后回读校验")
    args = ap.parse_args()

    all_ = build_all()
    names = args.targets or list(all_)
    unknown = [n for n in names if n not in all_]
    if unknown:
        print("未知目标:", ", ".join(unknown))
        sys.exit(1)

    out = Path(args.out)
    print(f"采样率 {SR}Hz · 目标目录 {out}\n")
    for name in names:
        path = out / f"{name}.wav"
        all_[name].save(path)
        if args.check or len(names) <= 4:
            _check(path)
    print(f"\n完成 {len(names)} 个文件。")


if __name__ == "__main__":
    main()
