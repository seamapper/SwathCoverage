"""Guard rails for raw file parsing to prevent hangs on corrupt data."""

import time


class ParseGuardError(ValueError):
    """Raised when parsing is aborted due to corrupt data, timeout, or user cancel."""


# Conservative physical limits for Kongsberg datagram fields.
MAX_ALL_RX_BEAMS = 1024
MAX_ALL_TX_SECTORS = 32
MAX_ALL_DG_LEN = 10 * 1024 * 1024
MAX_KMALL_TX_SECTORS = 16
MAX_KMALL_EXTRA_DET_CLASSES = 16
MAX_KMALL_SOUNDINGS = 4096
MAX_RESYNC_ERRORS = 10000
MAX_BYTE_SCAN_STALL = 10 * 1024 * 1024
FILE_PARSE_TIMEOUT_SEC = 600
_CANCEL_CHECK_INTERVAL = 10000

_cancelled = False
_file_parse_start = None


def reset_cancel():
    global _cancelled, _file_parse_start
    _cancelled = False
    _file_parse_start = None


def request_cancel():
    global _cancelled
    _cancelled = True


def is_cancelled():
    return _cancelled


def begin_file_parse():
    global _file_parse_start
    _file_parse_start = time.monotonic()


def check_cancel(loop_num=0):
    """Raise ParseGuardError if the user cancelled or the per-file timeout elapsed."""
    if _cancelled:
        raise ParseGuardError('Parsing cancelled by user')
    if loop_num and loop_num % _CANCEL_CHECK_INTERVAL == 0:
        if _file_parse_start is not None:
            elapsed = time.monotonic() - _file_parse_start
            if elapsed > FILE_PARSE_TIMEOUT_SEC:
                raise ParseGuardError(
                    f'File parse exceeded {FILE_PARSE_TIMEOUT_SEC}s timeout'
                )


def validate_all_dg_len(dg_len, len_raw):
    if dg_len < 3 or dg_len > MAX_ALL_DG_LEN or dg_len > len_raw:
        return False
    return True


def validate_beam_count(count, dg_len, entry_start, entry_length, name='NUM_RX_BEAMS'):
    max_by_size = max(0, (dg_len - entry_start - 4) // max(entry_length, 1))
    limit = min(MAX_ALL_RX_BEAMS, max_by_size)
    if count < 0 or count > limit:
        raise ParseGuardError(
            f'Invalid {name}: {count} (limit {limit} for datagram length {dg_len})'
        )
    return count


def validate_tx_sector_count(count, dg_len, entry_start=32, entry_length=24, name='NUM_TX_SECTORS'):
    max_by_size = max(0, (dg_len - entry_start - 4) // max(entry_length, 1))
    limit = min(MAX_ALL_TX_SECTORS, max_by_size)
    if count < 0 or count > limit:
        raise ParseGuardError(
            f'Invalid {name}: {count} (limit {limit} for datagram length {dg_len})'
        )
    return count


def validate_kmall_mrz_counts(num_tx_sectors, num_extra_classes, num_soundings, num_bytes_dgm, bytes_used):
    if num_tx_sectors < 0 or num_tx_sectors > MAX_KMALL_TX_SECTORS:
        raise ParseGuardError(f'Invalid numTxSectors: {num_tx_sectors}')
    if num_extra_classes < 0 or num_extra_classes > MAX_KMALL_EXTRA_DET_CLASSES:
        raise ParseGuardError(f'Invalid numExtraDetectionClasses: {num_extra_classes}')
    if num_soundings < 0 or num_soundings > MAX_KMALL_SOUNDINGS:
        raise ParseGuardError(f'Invalid sounding count: {num_soundings}')
    remaining = num_bytes_dgm - bytes_used
    if remaining < 0:
        raise ParseGuardError(
            f'MRZ header fields exceed datagram size ({num_bytes_dgm} bytes)'
        )


def record_resync_error(error_count, context=''):
    error_count += 1
    if error_count > MAX_RESYNC_ERRORS:
        detail = f' ({context})' if context else ''
        raise ParseGuardError(
            f'Too many resync errors ({error_count}) while parsing{detail}'
        )
    return error_count
