def collect():
    # 示例插件，返回基础采样数据
    return {
        "asn": "AS12345",
        "export_util": {"eth0": {"bps_in": 12345, "bps_out": 54321}},
        "env": {"temp": 27.5, "humidity": 45},
    }
