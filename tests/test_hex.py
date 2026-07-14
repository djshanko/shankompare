from shankompare.compare import count_differing_bytes, format_hex_line, hex_rows
from shankompare.compare.hex import HEX_WIDTH, ascii_char_span, hex_char_span


def test_identical_bytes_no_diffs():
    rows = hex_rows(b"hello world", b"hello world")
    assert len(rows) == 1
    assert rows[0].diff_bytes == ()
    assert not rows[0].is_diff


def test_single_byte_difference():
    left = bytes(range(32))
    right = bytearray(left)
    right[17] = 0xFF
    rows = hex_rows(left, bytes(right))
    assert len(rows) == 2
    assert rows[0].diff_bytes == ()
    assert rows[1].diff_bytes == (1,)  # byte 17 = row 1, index 1
    assert rows[1].offset == 16


def test_length_difference_marks_overhang():
    rows = hex_rows(b"abc", b"abcdef")
    assert rows[0].diff_bytes == (3, 4, 5)
    assert count_differing_bytes(rows) == 3


def test_empty_inputs():
    assert hex_rows(b"", b"") == []
    rows = hex_rows(b"", b"xy")
    assert rows[0].diff_bytes == (0, 1)
    assert rows[0].left == b""


def test_format_hex_line_layout():
    line = format_hex_line(0x1A2B, bytes(range(16)))
    assert line.startswith("00001a2b  00 01 02")
    assert line.endswith("|................|")
    # a short row pads to the same total width
    short = format_hex_line(0, b"Hi")
    assert len(short) == len(line)
    assert "|Hi" in short


def test_char_spans_point_at_the_right_characters():
    data = bytes(range(HEX_WIDTH))
    line = format_hex_line(0, data)
    for index in (0, 7, 15):
        start, end = hex_char_span(index)
        assert line[start:end] == f"{data[index]:02x}"
    start, end = ascii_char_span(0)
    assert line[start:end] == "."  # byte 0 is unprintable
    printable = format_hex_line(0, b"ABCDEFGHIJKLMNOP")
    start, end = ascii_char_span(2)
    assert printable[start:end] == "C"
