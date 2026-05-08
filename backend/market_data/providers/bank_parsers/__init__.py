"""Bank parser registry for the top Vietnamese savings-rate sources."""
from __future__ import annotations

BANKS: dict[str, dict[str, str]] = {
    "vcb": {"code": "VCB", "name": "Vietcombank"},
    "bidv": {"code": "BIDV", "name": "BIDV"},
    "agribank": {"code": "AGRIBANK", "name": "Agribank"},
    "vietinbank": {"code": "VIETINBANK", "name": "VietinBank"},
    "techcombank": {"code": "TCB", "name": "Techcombank"},
    "mbbank": {"code": "MBB", "name": "MBBank"},
    "acb": {"code": "ACB", "name": "ACB"},
    "vpbank": {"code": "VPB", "name": "VPBank"},
    "sacombank": {"code": "STB", "name": "Sacombank"},
    "hdbank": {"code": "HDB", "name": "HDBank"},
    "shb": {"code": "SHB", "name": "SHB"},
    "tpbank": {"code": "TPB", "name": "TPBank"},
    "ocb": {"code": "OCB", "name": "OCB"},
    "msb": {"code": "MSB", "name": "MSB"},
    "vib": {"code": "VIB", "name": "VIB"},
    "seabank": {"code": "SSB", "name": "SeABank"},
    "eximbank": {"code": "EIB", "name": "Eximbank"},
    "namabank": {"code": "NAB", "name": "Nam A Bank"},
    "bacabank": {"code": "BAB", "name": "Bac A Bank"},
    "lpbank": {"code": "LPB", "name": "LPBank"},
}
