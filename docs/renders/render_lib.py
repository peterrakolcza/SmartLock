"""Small offscreen VTK renderer for manifold3d parts (used by make_renders.py)."""

import numpy as np
import vtk
from PIL import Image, ImageDraw, ImageFont
from vtk.util.numpy_support import numpy_to_vtk, numpy_to_vtkIdTypeArray

PALETTE = {
    "adapter": (0.62, 0.64, 0.68),
    "hub": (0.20, 0.47, 0.86),
    "slider": (0.96, 0.58, 0.16),
    "fork": (0.22, 0.70, 0.36),
    "bracket": (0.55, 0.36, 0.78),
    "sg90": (0.16, 0.30, 0.72),
    "servo": (0.13, 0.13, 0.15),
    "door": (0.93, 0.92, 0.89),
    "metal": (0.72, 0.72, 0.70),
    "case": (0.55, 0.57, 0.60),
    "plate": (0.95, 0.95, 0.95),
    "battery": (0.25, 0.25, 0.28),
}


def polydata(part):
    # Long thin triangles (a cylinder wall next to a detailed cut-out) make smooth shading streak: split them first
    if hasattr(part, "refine_to_length"):
        part = part.refine_to_length(2.0)
    mesh = part.to_mesh()
    verts = np.ascontiguousarray(np.asarray(mesh.vert_properties)[:, :3], dtype=np.float64)
    tris = np.asarray(mesh.tri_verts, dtype=np.int64)
    cells = np.hstack([np.full((len(tris), 1), 3, dtype=np.int64), tris]).ravel()
    points = vtk.vtkPoints()
    points.SetData(numpy_to_vtk(verts, deep=True))
    polys = vtk.vtkCellArray()
    polys.SetCells(len(tris), numpy_to_vtkIdTypeArray(cells, deep=True))
    pd = vtk.vtkPolyData()
    pd.SetPoints(points)
    pd.SetPolys(polys)
    normals = vtk.vtkPolyDataNormals()
    normals.SetInputData(pd)
    normals.SetFeatureAngle(35)
    normals.SplittingOn()
    normals.Update()
    return normals.GetOutput()


class Scene:
    def __init__(self, width=1200, height=800, translucent=False):
        self.window = vtk.vtkRenderWindow()
        self.window.SetOffScreenRendering(1)
        self.window.SetSize(width, height)
        self.window.SetMultiSamples(0 if translucent else 8)
        self.renderer = vtk.vtkRenderer()
        self.window.AddRenderer(self.renderer)
        if translucent:  # correct see-through parts
            self.window.SetAlphaBitPlanes(1)
            self.renderer.SetUseDepthPeeling(1)
            self.renderer.SetMaximumNumberOfPeels(8)
        self.renderer.GradientBackgroundOn()
        self.renderer.SetBackground(0.97, 0.97, 0.98)
        self.renderer.SetBackground2(0.84, 0.86, 0.90)
        self.renderer.SetUseFXAA(True)
        kit = vtk.vtkLightKit()
        kit.SetKeyLightIntensity(0.9)
        kit.AddLightsToRenderer(self.renderer)
        self.actors = []

    def clear(self):
        for actor in self.actors:
            self.renderer.RemoveActor(actor)
        self.actors = []

    def add(self, part, color, opacity=1.0, specular=0.25):
        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputData(polydata(part))
        actor = vtk.vtkActor()
        actor.SetMapper(mapper)
        prop = actor.GetProperty()
        prop.SetColor(*(PALETTE.get(color, color) if isinstance(color, str) else color))
        prop.SetOpacity(opacity)
        prop.SetSpecular(specular)
        prop.SetSpecularPower(30)
        prop.SetDiffuse(0.85)
        prop.SetAmbient(0.18)
        self.renderer.AddActor(actor)
        self.actors.append(actor)
        return actor

    def camera(self, position, focal=(0, 0, 0), up=(0, 0, 1), angle=30):
        cam = self.renderer.GetActiveCamera()
        cam.SetPosition(*position)
        cam.SetFocalPoint(*focal)
        cam.SetViewUp(*up)
        cam.SetViewAngle(angle)
        self.renderer.ResetCameraClippingRange()

    def project(self, point):
        """World point -> pixel position in the rendered image."""
        self.window.Render()
        coord = vtk.vtkCoordinate()
        coord.SetCoordinateSystemToWorld()
        coord.SetValue(*point)
        x, y = coord.GetComputedDoubleDisplayValue(self.renderer)
        return x, self.window.GetSize()[1] - y

    def image(self):
        self.window.Render()
        grab = vtk.vtkWindowToImageFilter()
        grab.SetInput(self.window)
        grab.ReadFrontBufferOff()
        grab.Update()
        data = grab.GetOutput()
        w, h, _ = data.GetDimensions()
        arr = np.frombuffer(data.GetPointData().GetScalars(), dtype=np.uint8).reshape(h, w, -1)[::-1, :, :3]
        return Image.fromarray(arr.copy())


def font(size):
    for name in ("/System/Library/Fonts/Helvetica.ttc", "/System/Library/Fonts/SFNS.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def caption(img, title, subtitle=None, step=None):
    """Caption bar at the bottom of a frame."""
    img = img.copy()
    draw = ImageDraw.Draw(img, "RGBA")
    w, h = img.size
    bar = 92 if subtitle else 62
    draw.rectangle([0, h - bar, w, h], fill=(20, 24, 32, 215))
    x = 28
    if step:
        draw.rounded_rectangle([x, h - bar + 16, x + 40, h - bar + 56], 10, fill=(245, 150, 40, 255))
        draw.text((x + 20, h - bar + 36), step, font=font(26), fill="white", anchor="mm")
        x += 58
    draw.text((x, h - bar + 14), title, font=font(30), fill="white")
    if subtitle:
        draw.text((x, h - bar + 54), subtitle, font=font(21), fill=(200, 206, 216))
    return img


def label(img, text, xy, color=(30, 30, 30)):
    draw = ImageDraw.Draw(img, "RGBA")
    f = font(22)
    box = draw.textbbox(xy, text, font=f)
    draw.rounded_rectangle([box[0] - 8, box[1] - 5, box[2] + 8, box[3] + 5], 8, fill=(255, 255, 255, 220))
    draw.text(xy, text, font=f, fill=color)
    return img


def callout(img, scene, text, point, offset, anchor_px=None, label_px=None):
    """Label with a leader line to a 3D point; offset is the label position relative to the point in pixels."""
    draw = ImageDraw.Draw(img, "RGBA")
    px, py = anchor_px or scene.project(point)
    lx, ly = label_px or (px + offset[0], py + offset[1])
    f = font(22)
    box = draw.textbbox((lx, ly), text, font=f, anchor="mm")
    draw.line([(px, py), (lx, ly)], fill=(30, 34, 44, 230), width=2)
    draw.ellipse([px - 5, py - 5, px + 5, py + 5], fill=(245, 150, 40, 255), outline=(30, 34, 44, 255))
    draw.rounded_rectangle([box[0] - 10, box[1] - 6, box[2] + 10, box[3] + 6], 9, fill=(255, 255, 255, 235), outline=(30, 34, 44, 160))
    draw.text((lx, ly), text, font=f, fill=(25, 28, 36), anchor="mm")
    return img


def callouts(img, scene, items, margin=190, spacing=58):
    """Labels in a left and a right column, each pointing at a 3D point; the side follows the point."""
    w, h = img.size
    anchors = [(text, scene.project(point)) for text, point in items]
    for side in ("left", "right"):
        group = sorted([a for a in anchors if (a[1][0] < w / 2) == (side == "left")], key=lambda a: a[1][1])
        last_y = -1e9
        for text, (px, py) in group:
            ly = max(py, last_y + spacing)
            last_y = ly
            lx = margin if side == "left" else w - margin
            callout(img, scene, text, None, None, anchor_px=(px, py), label_px=(lx, ly))
    return img


def chips(img, items):
    """Status chips in the top left corner: [(text, (r, g, b)), ...]."""
    draw = ImageDraw.Draw(img, "RGBA")
    x, y = 22, 20
    f = font(22)
    for text, color in items:
        box = draw.textbbox((x + 30, y), text, font=f)
        draw.rounded_rectangle([x, y - 8, box[2] + 16, box[3] + 8], 16, fill=(255, 255, 255, 235), outline=(30, 34, 44, 120))
        draw.ellipse([x + 10, y + 3, x + 22, y + 15], fill=color)
        draw.text((x + 30, y), text, font=f, fill=(25, 28, 36))
        y += 48
    return img
