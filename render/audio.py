"""背景音乐与 UI 音效（pygame-ce mixer）。

设计要点：
- BGM 走 mixer.music 单流通道：deploy/battle 无缝循环；victory/defeat 一次性
  jingle 播完可自动回到部署曲。切歌用"淡出旧曲 -> 淡入新曲"，由主循环每帧
  调 update(dt) 驱动，绝不阻塞主线程。
- UI 音效走 mixer.Sound，首次使用时惰性加载并缓存。
- 无声卡 / 缺文件 / 初始化失败一律安全降级（enabled=False 或直接跳过播放），
  不抛异常、不影响游戏启动。音频资源由 tools/gen_audio.py 生成。
"""

from __future__ import annotations

from pathlib import Path

import pygame

AUDIO_DIR = Path(__file__).resolve().parents[1] / "assets" / "audio"

# 背景曲：曲名 -> (文件名, 是否循环)
BGM_TRACKS: dict[str, tuple[str, bool]] = {
    "deploy": ("bgm_deploy", True),  # 运营/布阵/结算待机循环
    "battle": ("bgm_battle", True),  # 开战循环
    "victory": ("bgm_victory", False),
    "defeat": ("bgm_defeat", False),
}

# UI 音效名 -> 文件名（都叫 sfx_<名字>.wav）
_SFX_NAMES = (
    "buy",
    "sell",
    "refresh",
    "lock",
    "equip",
    "combine",
    "star",
    "fight",
    "error",
)


class MusicManager:
    """单流背景乐：切换/一次性曲目 + 自动接续 + 淡入淡出 + 静音。"""

    FADE_OUT = 0.28  # 旧曲淡出时长（s）
    FADE_IN = 0.35  # 新曲淡入时长（s）

    def __init__(self, volume: float = 0.5) -> None:
        self.volume = volume
        self.muted = False
        self._cur: str | None = None
        self._loop = False
        self._after: str | None = None  # 一次性曲播完后续接的曲名
        self._pending: tuple | None = None  # 正在淡出，等停稳后开播的请求
        self._out_t = 0.0  # 淡出计时
        self._in_t = 0.0  # 淡入计时
        self._in_total = 0.0
        self._applied = 0.0  # 当前实际音量（避免每帧重复 set_volume）
        self._busy_seen = False  # 上一次 play 之后是否真的响起来过

    # ---- 对外 API ----

    def play(self, name: str, loop: bool = True) -> None:
        """切到某首循环曲。若目标曲已在播（且是循环曲）则忽略。"""
        if name not in BGM_TRACKS or name == self._cur:
            return
        self._request((name, loop, None))

    def play_once(self, name: str, after: str | None = None) -> None:
        """播一首一次性 jingle，结束后可选地接回 after 曲。"""
        if name not in BGM_TRACKS or name == self._cur:
            return
        self._request((name, False, after))

    def stop(self) -> None:
        self._pending = None
        self._cur = None
        self._loop = False
        self._after = None
        pygame.mixer.music.stop()

    def set_muted(self, muted: bool) -> None:
        self.muted = muted
        if self._cur is not None:
            self._apply(self._eff())

    # ---- 内部 ----

    def _eff(self) -> float:
        return 0.0 if self.muted else self.volume

    def _apply(self, v: float) -> None:
        if v != self._applied:
            self._applied = v
            pygame.mixer.music.set_volume(max(0.0, min(1.0, v)))

    def _request(self, target: tuple) -> None:
        self._pending = target
        if not pygame.mixer.music.get_busy() or self._cur is None:
            self._finish_pending()  # 当前无声，直接开播
            return
        # 停稳后播放：先把旧曲淡出
        pygame.mixer.music.fadeout(int(self.FADE_OUT * 1000))
        self._out_t = 0.0

    def _finish_pending(self) -> None:
        if self._pending is None:
            return
        name, loop, after = self._pending
        self._pending = None
        self._cur = name
        self._loop = loop
        self._after = after
        self._busy_seen = False
        path = AUDIO_DIR / f"{BGM_TRACKS[name][0]}.wav"
        try:
            pygame.mixer.music.load(str(path))
        except pygame.error:
            self._cur = None
            return
        pygame.mixer.music.play(-1 if loop else 0)
        self._in_total = self.FADE_IN
        self._in_t = 0.0
        self._applied = 0.0

    def update(self, dt: float) -> None:
        if self._pending is not None:
            # 等待旧曲淡出完成
            if pygame.mixer.music.get_busy():
                self._out_t += dt
                if self._out_t < self.FADE_OUT + 0.25:
                    return  # 还在淡出
            self._finish_pending()

        if self._cur is None:
            return

        target = self._eff()
        if self._in_total > 0.0:
            self._in_t += dt
            if self._in_t >= self._in_total:
                self._in_total = 0.0
                self._apply(target)
            else:
                self._apply(target * self._in_t / self._in_total)
            return

        if pygame.mixer.music.get_busy():
            self._busy_seen = True
            return
        # 当前没有在响：
        #  - 刚 play 还没起来 -> 等下一帧；
        #  - 一次性曲目播完了 -> 接续 after；循环曲意外停了 -> 重启。
        if not self._busy_seen:
            return
        after = self._after
        looping = self._loop
        name = self._cur
        self._cur = None
        self._busy_seen = False
        if after is not None:
            self._request((after, True, None))
        elif looping and name is not None:
            # 循环曲被中断：重开同一首
            self._request((name, True, None))


class SfxManager:
    """短音效：惰性加载 Sound 并缓存，失败记一次警告后静默跳过。"""

    def __init__(self, volume: float = 0.55) -> None:
        self.volume = volume
        self.muted = False
        self._sounds: dict[str, pygame.mixer.Sound | None] = {}
        self._warned: set[str] = set()

    def play(self, name: str) -> None:
        if self.muted or name not in _SFX_NAMES:
            return
        snd = self._load(name)
        if snd is not None:
            snd.play()

    def set_muted(self, muted: bool) -> None:
        self.muted = muted

    def _load(self, name: str) -> pygame.mixer.Sound | None:
        snd = self._sounds.get(name, ...)
        if snd is not ...:
            return snd
        snd = None
        path = AUDIO_DIR / f"sfx_{name}.wav"
        try:
            snd = pygame.mixer.Sound(str(path))
            snd.set_volume(self.volume)
        except (pygame.error, FileNotFoundError):
            if name not in self._warned:
                self._warned.add(name)
                print(f"[音效] 无法加载 {path.name}，已跳过该音效")
        self._sounds[name] = snd
        return snd


class Audio:
    """聚合入口：初始化失败则整体禁用（游戏照常跑）。"""

    def __init__(self) -> None:
        self.enabled = pygame.mixer.get_init() is not None
        self.music = MusicManager() if self.enabled else None
        self.sfx = SfxManager() if self.enabled else None
        if not self.enabled:
            print("[音效] 未检测到音频设备，本次静音运行")

    def update(self, dt: float) -> None:
        if self.enabled:
            self.music.update(dt)

    def toggle_muted(self) -> bool:
        """切换静音，返回切换后状态（禁用时恒为 False）。"""
        if not self.enabled:
            return False
        muted = not self.music.muted
        self.music.set_muted(muted)
        self.sfx.set_muted(muted)
        return muted
