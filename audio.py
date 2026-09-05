"""Read an audio file's native sample rate without decoding it.

The mixer resamples anything that does not match the rate it was opened at, and
SDL's resampler is not length-preserving -- a 48 kHz song played through a
44.1 kHz mixer comes out 0.13% short, which is 190 ms of drift over two and a
half minutes. Opening the mixer at the file's own rate removes the resampler
from the chain entirely, so this only has to look at the header.

Returns None for anything it does not recognise; the caller keeps its default.
"""

import os
import struct

# [version][index], where version is 1 for MPEG-1, 2 for MPEG-2, 25 for MPEG-2.5
MPEG_RATES = {
    1: [44100, 48000, 32000, None],
    2: [22050, 24000, 16000, None],
    25: [11025, 12000, 8000, None],
}
MPEG_VERSION = {3: 1, 2: 2, 0: 25}


def _id3_end(data):
    """Byte offset of the first frame, past any ID3v2 tag."""
    if data[:3] != b"ID3" or len(data) < 10:
        return 0
    # A syncsafe size: four 7-bit groups, so no byte can look like a frame sync.
    size = data[6] << 21 | data[7] << 14 | data[8] << 7 | data[9]
    return 10 + size


# Layer III bitrates in kbps, by MPEG version family.
MPEG_BITRATES = {
    1: [None, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, None],
    2: [None, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160, None],
}


def _mp3_frame(data, i):
    """(sample rate, frame length) if a Layer III frame starts at `i`, else None."""
    if i + 4 > len(data) or data[i] != 0xFF or (data[i + 1] & 0xE0) != 0xE0:
        return None
    version = MPEG_VERSION.get((data[i + 1] >> 3) & 3)
    if version is None or (data[i + 1] >> 1) & 3 != 1:  # layer bits 01 == Layer III
        return None
    bitrate = MPEG_BITRATES[1 if version == 1 else 2][(data[i + 2] >> 4) & 15]
    rate = MPEG_RATES[version][(data[i + 2] >> 2) & 3]
    if not bitrate or not rate:
        return None
    padding = (data[i + 2] >> 1) & 1
    # MPEG-1 Layer III carries 1152 samples per frame, MPEG-2 and 2.5 carry 576.
    length = (144 if version == 1 else 72) * bitrate * 1000 // rate + padding
    return (rate, length) if length > 4 else None


def _mp3_rate(data):
    """Rate of the first frame that is followed by two more at the right spacing.

    A lone sync pattern turns up in plenty of binary files, so the chain is what
    separates an actual mp3 from a font that happens to contain 0xFF 0xFB.
    """
    i = _id3_end(data)
    limit = min(len(data) - 4, i + 200000)
    while i < limit:
        frame = _mp3_frame(data, i)
        if frame:
            rate, length = frame
            offset = i
            for _ in range(2):
                offset += length
                nxt = _mp3_frame(data, offset)
                if not nxt or nxt[0] != rate:
                    frame = None
                    break
                length = nxt[1]
            if frame:
                return rate
        i += 1
    return None


def _wav_rate(data):
    if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        return None
    i = 12
    while i + 8 <= len(data):
        chunk, size = data[i:i + 4], struct.unpack("<I", data[i + 4:i + 8])[0]
        if chunk == b"fmt " and i + 16 <= len(data):
            return struct.unpack("<I", data[i + 12:i + 16])[0]
        i += 8 + size + (size & 1)  # chunks are word aligned
    return None


def _ogg_rate(data):
    if data[:4] != b"OggS":
        return None
    segments = data[26]
    body = 27 + segments
    packet = data[body:body + 32]
    if packet[:7] == b"\x01vorbis":
        return struct.unpack("<I", packet[12:16])[0]
    if packet[:8] == b"OpusHead":
        return 48000  # Opus always decodes at 48 kHz whatever the input rate was
    return None


def _flac_rate(data):
    if data[:4] != b"fLaC":
        return None
    block = data[8:8 + 34]  # skip the 4-byte metadata block header to STREAMINFO
    if len(block) < 13:
        return None
    bits = block[10] << 16 | block[11] << 8 | block[12]
    return (bits >> 4) or None


READERS = (_wav_rate, _flac_rate, _ogg_rate, _mp3_rate)


def native_rate(path):
    """The file's own sample rate in Hz, or None if it cannot be determined."""
    try:
        with open(path, "rb") as file:
            head = file.read(65536)
    except OSError:
        return None
    for reader in READERS:
        try:
            rate = reader(head)
        except (IndexError, struct.error):
            continue
        if rate and 4000 <= rate <= 192000:
            return rate
    return None
