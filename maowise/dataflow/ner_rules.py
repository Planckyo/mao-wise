from __future__ import annotations

import re
from typing import Dict, Any


_num = r"(?:(?:\d+\.\d+)|(?:\d+))"

PATTERNS = {
    "voltage_V": re.compile(rf"(?:电压|voltage)\s*[:=]?\s*({_num})\s*(?:V|伏)", re.I),
    "current_density_A_dm2": re.compile(rf"(?:电流密度|current\s*density)\s*[:=]?\s*({_num})\s*A\s*/\s*(?:dm\^?2|dm2)", re.I),
    "frequency_Hz": re.compile(rf"(?:频率|frequency)\s*[:=]?\s*({_num})\s*Hz", re.I),
    "duty_cycle_pct": re.compile(rf"(?:占空比|duty\s*cycle)\s*[:=]?\s*({_num})\s*(?:%|percent)", re.I),
    "time_min": re.compile(rf"(?:时间|time)\s*[:=]?\s*({_num})\s*(?:min|分钟)", re.I),
    "temp_C": re.compile(rf"(?:温度|temperature)\s*[:=]?\s*({_num})\s*(?:°?C)", re.I),
    "pH": re.compile(rf"(?:pH)\s*[:=]?\s*({_num})", re.I),
    "alpha_150_2600": re.compile(rf"(?:α|alpha)\s*(?:\(150[-–]2600\s*nm\))?\s*[:=]?\s*({_num})", re.I),
    "epsilon_3000_30000": re.compile(rf"(?:ε|epsilon)\s*(?:\(3000[-–]30000\s*nm\))?\s*[:=]?\s*({_num})", re.I),
}


def extract_fields_from_text(text: str) -> Dict[str, Any]:
    rec: Dict[str, Any] = {}
    for k, pat in PATTERNS.items():
        m = pat.search(text)
        if m:
            try:
                rec[k] = float(m.group(1))
            except Exception:
                pass
    # Simple guesses for enums
    if re.search(r"silicate|硅酸盐", text, re.I):
        rec["electrolyte_family"] = "silicate"
    elif re.search(r"phosphate|磷酸盐", text, re.I):
        rec["electrolyte_family"] = "phosphate"

    if re.search(r"bipolar|双极", text, re.I):
        rec["mode"] = "bipolar"
    elif re.search(r"unipolar|单极", text, re.I):
        rec["mode"] = "unipolar"
    elif re.search(r"dc|直流", text, re.I):
        rec["mode"] = "dc"

    return rec

