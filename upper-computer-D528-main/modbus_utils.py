# modbus_utils.py
"""
Modbus RTU 工具层

职责：
1. 计算 Modbus RTU CRC16
2. 从串口 raw bytes 中拼出完整帧
3. 过滤错位帧、半包、粘包、CRC 错包

业务层不要直接相信 serial.read() 返回的数据
业务层只处理 ModbusFrameParser.feed() 吐出的完整合法 frame
"""


def calculate_crc16(data: bytes) -> bytes:
    """计算 Modbus RTU CRC16 校验码，返回 little-endian 两字节"""
    crc = 0xFFFF

    for pos in data:
        crc ^= pos
        for _ in range(8):
            if (crc & 1) != 0:
                crc >>= 1
                crc ^= 0xA001
            else:
                crc >>= 1

    return crc.to_bytes(2, byteorder="little")


class ModbusFrameParser:
    """Modbus RTU 拼包器：从串口 raw bytes 中吐出完整且 CRC 正确的帧"""

    def __init__(self, valid_addrs=range(1, 10), valid_funcs=(0x03, 0x04), max_buffer_size=512):
        self.buffer = bytearray()
        self.valid_addrs = set(valid_addrs)
        self.valid_funcs = set(valid_funcs)
        self.max_buffer_size = max_buffer_size

    def feed(self, data: bytes) -> list[bytes]:
        """输入串口 raw bytes，返回 0 个或多个完整合法 Modbus response frame"""
        frames = []

        if not data:
            return frames

        self.buffer.extend(data)

        while len(self.buffer) >= 5:
            addr = self.buffer[0]
            func = self.buffer[1]

            # 错位保护：站号不合法，丢 1 byte 重新找帧头
            if addr not in self.valid_addrs:
                self.buffer.pop(0)
                continue

            # 功能码不合法，丢 1 byte 重新找帧头
            if func not in self.valid_funcs:
                self.buffer.pop(0)
                continue

            # 标准 Modbus response:
            # addr + func + byte_count + payload + crc_low + crc_high
            byte_count = self.buffer[2]
            expected_len = 3 + byte_count + 2

            # 长度不够，等下一次串口数据
            if len(self.buffer) < expected_len:
                break

            frame = bytes(self.buffer[:expected_len])

            # CRC 正确才交给业务层
            if frame[-2:] == calculate_crc16(frame[:-2]):
                frames.append(frame)
                del self.buffer[:expected_len]
            else:
                # CRC 错，当前帧头可能是假头，丢 1 byte 重新同步
                self.buffer.pop(0)

        # 防止异常垃圾数据无限堆积
        if len(self.buffer) > self.max_buffer_size:
            self.buffer.clear()

        return frames

    def clear(self):
        """手动清空缓冲区"""
        self.buffer.clear()