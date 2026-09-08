"""数据文件完整性门禁：所有数值改动必须能通过 check_data。"""

from core.dataio import check_data, clear_cache


def test_all_data_files_are_consistent():
    clear_cache()  # 强制从磁盘重新读取，避免缓存掩盖磁盘改动
    errors = check_data()
    assert errors == [], "数据自检未通过：\n" + "\n".join(errors)
