
from flask import Flask, render_template, request, jsonify, send_file
from dataclasses import dataclass
from pathlib import Path
import tempfile
import os
import zipfile
import socket

import ezdxf
import rhino3dm

app = Flask(__name__)


@dataclass
class Settings:
    width: float = 200.0
    depth: float = 200.0
    height: float = 100.0
    thickness: float = 3.0
    sheet_width: float = 500.0
    sheet_height: float = 300.0
    kerf: float = 0.15
    fit_difference: float = 0.01
    fingers: int = 4
    margin: float = 8.0


def validate(s):
    if min(
        s.width, s.depth, s.height, s.thickness,
        s.sheet_width, s.sheet_height
    ) <= 0:
        raise ValueError("Todas las dimensiones deben ser mayores que 0.")

    if s.kerf < 0:
        raise ValueError("El kerf no puede ser negativo.")

    if s.fit_difference < 0:
        raise ValueError("La diferencia del hueco no puede ser negativa.")

    if s.fit_difference >= s.thickness:
        raise ValueError("La diferencia del hueco debe ser menor que el espesor del MDF.")

    if s.fingers < 1:
        raise ValueError("Usá al menos 1 diente por lado.")

    shortest = min(s.width, s.depth, s.height)
    segment_count = 2 * s.fingers + 1
    if shortest / segment_count < max(2.0, s.thickness * 0.8):
        raise ValueError("Hay demasiados dientes para una de las dimensiones.")


def bbox(points):
    xs = [x for x, y in points]
    ys = [y for x, y in points]
    return min(xs), min(ys), max(xs), max(ys)


def add_unique(target, point):
    p = (round(point[0], 6), round(point[1], 6))
    if not target or p != target[-1]:
        target.append(p)


def profiled_edge(p0, p1, outward, mode, teeth, male_depth, female_depth):
    """
    teeth = cantidad real de dientes/huecos.
    Se usan 2*teeth+1 segmentos para dejar extremos planos.

    male: sobresale exactamente male_depth.
    female: entra exactamente female_depth.
    """
    x0, y0 = p0
    x1, y1 = p1

    dx = x1 - x0
    dy = y1 - y0
    length = (dx * dx + dy * dy) ** 0.5

    if length == 0:
        return [p0]

    if mode == "flat":
        return [p0, p1]

    ux = dx / length
    uy = dy / length
    nx, ny = outward

    segments = 2 * teeth + 1
    step = length / segments
    depth = male_depth if mode == "male" else female_depth
    sign = 1.0 if mode == "male" else -1.0

    pts = [p0]

    for i in range(segments):
        a = i * step
        b = (i + 1) * step
        active = (i % 2 == 1)

        ax = x0 + ux * a
        ay = y0 + uy * a
        bx = x0 + ux * b
        by = y0 + uy * b

        add_unique(pts, (ax, ay))

        if active:
            off = sign * depth
            add_unique(pts, (ax + nx * off, ay + ny * off))
            add_unique(pts, (bx + nx * off, by + ny * off))

        add_unique(pts, (bx, by))

    return pts


def panel_outline(w, h, teeth, bottom, right, top, left, male_depth, female_depth):
    edges = [
        ((0, 0), (w, 0), (0, -1), bottom),
        ((w, 0), (w, h), (1, 0), right),
        ((w, h), (0, h), (0, 1), top),
        ((0, h), (0, 0), (-1, 0), left),
    ]

    out = []
    for p0, p1, normal, mode in edges:
        edge = profiled_edge(
            p0, p1, normal, mode, teeth,
            male_depth, female_depth
        )
        for point in edge:
            add_unique(out, point)

    if out[-1] != out[0]:
        out.append(out[0])

    return out


def create_parts(s):
    W = s.width
    D = s.depth
    H = s.height
    teeth = s.fingers

    # REGLA PEDIDA:
    # MDF 3.00 mm -> pestaña 3.00 mm
    # hueco 3.00 - 0.01 = 2.99 mm
    male_depth = s.thickness
    female_depth = s.thickness - s.fit_difference

    front = panel_outline(
        W, H, teeth,
        bottom="female", right="male", top="female", left="male",
        male_depth=male_depth, female_depth=female_depth
    )

    back = panel_outline(
        W, H, teeth,
        bottom="female", right="male", top="female", left="male",
        male_depth=male_depth, female_depth=female_depth
    )

    left_panel = panel_outline(
        D, H, teeth,
        bottom="female", right="female", top="female", left="female",
        male_depth=male_depth, female_depth=female_depth
    )

    right_panel = panel_outline(
        D, H, teeth,
        bottom="female", right="female", top="female", left="female",
        male_depth=male_depth, female_depth=female_depth
    )

    base = panel_outline(
        W, D, teeth,
        bottom="male", right="male", top="male", left="male",
        male_depth=male_depth, female_depth=female_depth
    )

    lid = panel_outline(
        W, D, teeth,
        bottom="male", right="male", top="male", left="male",
        male_depth=male_depth, female_depth=female_depth
    )

    return [
        ("01_FRENTE", front),
        ("02_FONDO", back),
        ("03_LATERAL_IZQ", left_panel),
        ("04_LATERAL_DER", right_panel),
        ("05_BASE", base),
        ("06_TAPA", lid),
    ]


def pack_parts(parts, s):
    placed = []
    sheet = 1
    x = s.margin
    y = s.margin
    row_h = 0.0

    for name, points in parts:
        x0, y0, x1, y1 = bbox(points)
        w = x1 - x0
        h = y1 - y0

        if w + 2 * s.margin > s.sheet_width or h + 2 * s.margin > s.sheet_height:
            raise ValueError(
                f"{name} no entra en una plancha de "
                f"{s.sheet_width:g} x {s.sheet_height:g} mm."
            )

        if x + w + s.margin > s.sheet_width:
            x = s.margin
            y += row_h + s.margin
            row_h = 0.0

        if y + h + s.margin > s.sheet_height:
            sheet += 1
            x = s.margin
            y = s.margin
            row_h = 0.0

        shifted = [(px - x0 + x, py - y0 + y) for px, py in points]

        placed.append({
            "sheet": sheet,
            "name": name,
            "points": shifted
        })

        x += w + s.margin
        row_h = max(row_h, h)

    return placed, sheet


def settings_from_json(data):
    s = Settings(
        width=float(data.get("width", 200)),
        depth=float(data.get("depth", 200)),
        height=float(data.get("height", 100)),
        thickness=float(data.get("thickness", 3)),
        sheet_width=float(data.get("sheet_width", 500)),
        sheet_height=float(data.get("sheet_height", 300)),
        kerf=float(data.get("kerf", 0.15)),
        fit_difference=float(data.get("fit_difference", 0.01)),
        fingers=int(data.get("fingers", 4)),
    )
    validate(s)
    return s


def export_dxf(items, path):
    doc = ezdxf.new("R2010")
    doc.units = ezdxf.units.MM

    if "CORTE" not in doc.layers:
        doc.layers.new("CORTE")

    msp = doc.modelspace()

    for item in items:
        msp.add_lwpolyline(
            item["points"],
            close=True,
            dxfattribs={"layer": "CORTE"}
        )

    doc.saveas(path)


def export_3dm(items, path):
    doc = rhino3dm.File3dm()
    doc.Settings.ModelUnitSystem = rhino3dm.UnitSystem.Millimeters

    layer = rhino3dm.Layer()
    layer.Name = "CORTE"
    layer_index = doc.Layers.Add(layer)

    attrs = rhino3dm.ObjectAttributes()
    attrs.LayerIndex = layer_index

    for item in items:
        poly = rhino3dm.Polyline(
            [rhino3dm.Point3d(x, y, 0.0) for x, y in item["points"]]
        )
        doc.Objects.AddPolyline(poly, attrs)

    if not doc.Write(str(path), 7):
        raise RuntimeError("No se pudo crear el archivo 3DM.")


@app.get("/")
def index():
    return render_template("index.html")


@app.post("/api/preview")
def api_preview():
    try:
        data = request.get_json(force=True)
        s = settings_from_json(data)
        items, sheet_count = pack_parts(create_parts(s), s)

        return jsonify({
            "ok": True,
            "sheet_count": sheet_count,
            "items": items,
            "male_depth": s.thickness,
            "female_depth": s.thickness - s.fit_difference,
            "sheet_width": s.sheet_width,
            "sheet_height": s.sheet_height,
        })

    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.post("/api/export")
def api_export():
    try:
        data = request.get_json(force=True)
        s = settings_from_json(data)
        items, _ = pack_parts(create_parts(s), s)

        temp_dir = Path(tempfile.mkdtemp(prefix="laserjoin_"))

        dxf_path = temp_dir / "laserjoin_box_mobile.dxf"
        threedm_path = temp_dir / "laserjoin_box_mobile.3dm"
        zip_path = temp_dir / "LaserJoin_Project.zip"

        export_dxf(items, dxf_path)
        export_3dm(items, threedm_path)

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(dxf_path, dxf_path.name)
            z.write(threedm_path, threedm_path.name)

        return send_file(
            zip_path,
            as_attachment=True,
            download_name="LaserJoin_Project.zip",
            mimetype="application/zip"
        )

    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


def local_ip():
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
        sock.close()
        return ip
    except Exception:
        return "TU_IP_LOCAL"


if __name__ == "__main__":
    ip = local_ip()
    print()
    print("==============================================")
    print(" LASERJOIN STUDIO WEB MOBILE")
    print("==============================================")
    print("En esta PC:")
    print("http://127.0.0.1:5000")
    print()
    print("En tu celular, conectado al mismo Wi-Fi:")
    print(f"http://{ip}:5000")
    print()
    print("Deja esta ventana abierta mientras uses la app.")
    print("==============================================")
    print()
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)
