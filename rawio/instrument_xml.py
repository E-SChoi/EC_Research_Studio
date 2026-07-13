
from pathlib import Path
import xml.etree.ElementTree as ET
import numpy as np


NATIVE_EXTENSIONS = {
    "DPV": [".mtd"],
    "SWV": [".mts"],
    "EIS": [".mteisp"],
}


def _float_array(text):
    if text is None:
        return np.array([], dtype=float)

    values = []
    for token in text.replace("\n", "").split(","):
        token = token.strip()
        if not token:
            continue
        values.append(float(token))
    return np.asarray(values, dtype=float)


def _curves(path):
    path = Path(path)
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        raise ValueError(f"Invalid instrument XML file: {path.name}") from exc

    curves = root.findall(".//curve")
    if not curves:
        raise ValueError(f"No curves found in instrument file: {path.name}")
    return curves


def curve_summary(path):
    """Return compact metadata for every stored curve."""
    rows = []
    for index, curve in enumerate(_curves(path), start=1):
        technic = curve.find("technic")
        rows.append({
            "curve_number": index,
            "name": curve.findtext("name", default=""),
            "technique": technic.attrib.get("id", "") if technic is not None else "",
            "eis_curve_type": curve.findtext("TypeEISCurve", default=""),
        })
    return rows


def read_last_voltammetry_curve(path, expected_technique=None):
    """
    Read the last DPV/SWV curve stored in an instrument-native XML file.

    The displayed differential current is reconstructed as i1 - i2,
    matching the instrument CSV export.
    """
    curves = _curves(path)

    candidates = []
    for curve in curves:
        technic = curve.find("technic")
        technique = technic.attrib.get("id", "").upper() if technic is not None else ""
        if expected_technique is None or technique == expected_technique.upper():
            candidates.append(curve)

    if not candidates:
        raise ValueError(
            f"No {expected_technique or 'voltammetry'} curves found in {Path(path).name}"
        )

    curve = candidates[-1]
    points = curve.find("points")
    if points is None:
        raise ValueError(f"No point data found in last curve of {Path(path).name}")

    potential = _float_array(points.findtext("potential"))
    i1 = _float_array(points.findtext("i1"))
    i2 = _float_array(points.findtext("i2"))

    n = min(len(potential), len(i1), len(i2))
    if n < 5:
        raise ValueError(f"Insufficient points in last curve of {Path(path).name}")

    potential = potential[:n]
    current = i1[:n] - i2[:n]

    return {
        "potential": potential,
        "current": current,
        "curve_name": curve.findtext("name", default=""),
        "technique": (
            curve.find("technic").attrib.get("id", "")
            if curve.find("technic") is not None
            else ""
        ),
        "stored_curve_count": len(curves),
        "selected_curve_number": curves.index(curve) + 1,
    }


def read_last_eis_nyquist_curve(path):
    """
    Read the last Nyquist curve stored in a .mteisp file.

    Instrument fields:
    - potential -> Z' (ohm)
    - i1        -> -Z'' (ohm)
    - time      -> frequency (Hz)
    """
    curves = _curves(path)

    nyquist = [
        curve
        for curve in curves
        if curve.findtext("TypeEISCurve", default="").upper() == "NYQUIST"
    ]

    if not nyquist:
        raise ValueError(f"No Nyquist curve found in {Path(path).name}")

    curve = nyquist[-1]
    points = curve.find("points")
    if points is None:
        raise ValueError(f"No point data found in last Nyquist curve of {Path(path).name}")

    frequency = _float_array(points.findtext("time"))
    z_real = _float_array(points.findtext("potential"))
    z_imag = _float_array(points.findtext("i1"))

    n = min(len(frequency), len(z_real), len(z_imag))
    if n < 5:
        raise ValueError(f"Insufficient EIS points in {Path(path).name}")

    return {
        "z_real": z_real[:n],
        "z_imag": z_imag[:n],
        "frequency": frequency[:n],
        "curve_name": curve.findtext("name", default=""),
        "stored_curve_count": len(curves),
        "selected_curve_number": curves.index(curve) + 1,
    }


def native_method_for_suffix(path):
    suffix = Path(path).suffix.lower()
    for method, extensions in NATIVE_EXTENSIONS.items():
        if suffix in extensions:
            return method
    return None
