# ============================================================
#  Archi CAD Tools — Blender Add-on
#  柱・壁を数値入力(mm)で生成する建築モデリング補助ツール
#  Blender 4.x 対応
# ============================================================

bl_info = {
    "name": "Archi CAD Tools",
    "author": "Kenshin Design Office",
    "version": (0, 2, 0),
    "blender": (4, 0, 0),
    "location": "3D Viewport > Sidebar > Archi CAD",
    "description": "柱・壁などの建築要素を寸法(mm)指定で生成",
    "category": "Mesh",
}

import bpy
import bmesh
import math
from bpy.props import (
    FloatProperty,
    IntProperty,
    EnumProperty,
    BoolProperty,
    FloatVectorProperty,
    StringProperty,
    PointerProperty,
)
from bpy_extras import view3d_utils
from mathutils import Vector


# ------------------------------------------------------------------ #
#  ユーティリティ
# ------------------------------------------------------------------ #

def mm(val):
    """mm → Blender内部単位(m)"""
    return val / 1000.0


# 窓の上端FL高さ（op_height + sill_height の合計を固定）
_WINDOW_TOTAL_H = 2000.0
_window_updating = False  # 循環更新を防ぐフラグ


def _on_op_height_change(self, context):
    global _window_updating
    if _window_updating:
        return
    _window_updating = True
    self.sill_height = max(0.0, _WINDOW_TOTAL_H - self.op_height)
    _window_updating = False


def _on_sill_height_change(self, context):
    global _window_updating
    if _window_updating:
        return
    _window_updating = True
    self.op_height = max(100.0, _WINDOW_TOTAL_H - self.sill_height)
    _window_updating = False


def _bm_refresh(bm):
    """bisect後のルックアップテーブルを一括更新"""
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bm.faces.ensure_lookup_table()


def _bisect(bm, co, no):
    """bisect_plane を実行してルックアップテーブルを更新"""
    geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
    bmesh.ops.bisect_plane(bm, geom=geom, plane_co=co, plane_no=no)
    _bm_refresh(bm)


def _pref_material(pref_key):
    """AddonPreferences で指定されたマテリアルを返す。未設定・不在なら None。"""
    addon = bpy.context.preferences.addons.get(__name__)
    if addon is None:
        return None
    mat_name = getattr(addon.preferences, pref_key, "")
    if not mat_name:
        return None
    return bpy.data.materials.get(mat_name)


def apply_material(obj, name, color, pref_key=""):
    """マテリアルを適用。pref_key が指定されていれば設定値を優先する。"""
    mat = _pref_material(pref_key) if pref_key else None
    if mat is None:
        mat = bpy.data.materials.get(name)
        if mat is None:
            mat = bpy.data.materials.new(name=name)
            mat.use_nodes = True
            bsdf = mat.node_tree.nodes.get("Principled BSDF")
            if bsdf:
                bsdf.inputs["Base Color"].default_value = color
    if obj.data.materials:
        obj.data.materials[0] = mat
    else:
        obj.data.materials.append(mat)


def get_or_create_collection(col_name, context):
    """指定名のコレクションを取得、なければ新規作成してシーンにリンクする。"""
    col = bpy.data.collections.get(col_name)
    if col is None:
        col = bpy.data.collections.new(col_name)
        context.scene.collection.children.link(col)
    return col


def link_to_named_collection(obj, col_name, context):
    """オブジェクトを指定名のコレクションへ移動する（既存コレクションからアンリンク）。"""
    col = get_or_create_collection(col_name, context)
    for c in list(obj.users_collection):
        c.objects.unlink(obj)
    col.objects.link(obj)


# モーダル中にビューナビゲーション（ズーム・パン・回転）へ素通しするイベント
_NAV_EVENTS = {
    'MIDDLEMOUSE',
    'WHEELUPMOUSE', 'WHEELDOWNMOUSE',
    'WHEELINMOUSE', 'WHEELOUTMOUSE',
    'NUMPAD_1', 'NUMPAD_2', 'NUMPAD_3',
    'NUMPAD_4', 'NUMPAD_5', 'NUMPAD_6',
    'NUMPAD_7', 'NUMPAD_8', 'NUMPAD_9',
    'NUMPAD_0', 'NUMPAD_PERIOD',
    'NUMPAD_PLUS', 'NUMPAD_MINUS',
}

# 数値入力キー（通常キーボード）→ 文字マッピング
_NUM_KEYS = {
    'ZERO': '0', 'ONE': '1', 'TWO': '2', 'THREE': '3', 'FOUR': '4',
    'FIVE': '5', 'SIX': '6', 'SEVEN': '7', 'EIGHT': '8', 'NINE': '9',
    'PERIOD': '.', 'COMMA': '.',
}


def snap_to_grid(point, context):
    """グリッドスナップが有効なら最近傍グリッド交点に丸める"""
    props = context.scene.archicad
    if not props.snap_enabled:
        return point
    sx = mm(props.snap_span_x)
    sy = mm(props.snap_span_y)
    if sx <= 0 or sy <= 0:
        return point
    snapped_x = round(point.x / sx) * sx
    snapped_y = round(point.y / sy) * sy
    return Vector((snapped_x, snapped_y, point.z))


def _make_pillar_bm(w, d, h, shape, segments):
    """柱の BMesh を生成して返す (w/d/h は Blender 単位=m)"""
    bm = bmesh.new()
    if shape == 'RECT':
        vb = [
            bm.verts.new((-w/2, -d/2, 0)), bm.verts.new(( w/2, -d/2, 0)),
            bm.verts.new(( w/2,  d/2, 0)), bm.verts.new((-w/2,  d/2, 0)),
        ]
        vt = [
            bm.verts.new((-w/2, -d/2, h)), bm.verts.new(( w/2, -d/2, h)),
            bm.verts.new(( w/2,  d/2, h)), bm.verts.new((-w/2,  d/2, h)),
        ]
        bm.faces.new(vb); bm.faces.new(vt[::-1])
        for i in range(4):
            ni = (i + 1) % 4
            bm.faces.new([vb[i], vb[ni], vt[ni], vt[i]])
    else:
        r = w / 2
        vb, vt = [], []
        for i in range(segments):
            ang = 2 * math.pi * i / segments
            x, y = r * math.cos(ang), r * math.sin(ang)
            vb.append(bm.verts.new((x, y, 0)))
            vt.append(bm.verts.new((x, y, h)))
        bm.faces.new(vb); bm.faces.new(vt[::-1])
        for i in range(segments):
            ni = (i + 1) % segments
            bm.faces.new([vb[i], vb[ni], vt[ni], vt[i]])
    return bm


# ------------------------------------------------------------------ #
#  シーンプロパティ（グリッドスナップ設定）
# ------------------------------------------------------------------ #

class ARCHICAD_SceneProps(bpy.types.PropertyGroup):
    snap_enabled: BoolProperty(
        name="グリッドスナップ",
        default=False,
        description="通り芯グリッドに吸着して配置",
    )
    snap_span_x: FloatProperty(
        name="Xスパン (mm)",
        default=910, min=1, max=100000,
        description="X方向グリッド間隔 (mm)",
    )
    snap_span_y: FloatProperty(
        name="Yスパン (mm)",
        default=910, min=1, max=100000,
        description="Y方向グリッド間隔 (mm)",
    )


# ------------------------------------------------------------------ #
#  柱 (Pillar) オペレーター
# ------------------------------------------------------------------ #

class ARCHICAD_OT_add_pillar(bpy.types.Operator):
    """柱を生成（mm指定）"""
    bl_idname = "archicad.add_pillar"
    bl_label = "柱を追加"
    bl_options = {'REGISTER', 'UNDO'}

    width: FloatProperty(
        name="幅 X (mm)", default=105, min=1, max=10000,
        description="柱の幅（X方向）mm"
    )
    depth: FloatProperty(
        name="奥行 Y (mm)", default=105, min=1, max=10000,
        description="柱の奥行（Y方向）mm"
    )
    height: FloatProperty(
        name="高さ Z (mm)", default=2800, min=1, max=50000,
        description="柱の高さ（Z方向）mm"
    )
    shape: EnumProperty(
        name="断面形状",
        items=[
            ('RECT', '角柱', '四角い柱'),
            ('CIRCLE', '丸柱', '円形の柱'),
        ],
        default='RECT',
    )
    segments: IntProperty(
        name="円の分割数", default=32, min=8, max=128,
        description="丸柱の円周分割数"
    )
    loc: FloatVectorProperty(
        name="配置位置 (mm)",
        default=(0, 0, 0),
        description="X, Y, Z 座標 (mm)",
        size=3,
    )
    auto_material: BoolProperty(
        name="自動マテリアル", default=True,
        description="木材風マテリアルを自動適用"
    )

    def execute(self, context):
        lx, ly, lz = mm(self.loc[0]), mm(self.loc[1]), mm(self.loc[2])
        bm = _make_pillar_bm(mm(self.width), mm(self.depth), mm(self.height),
                              self.shape, self.segments)
        mesh = bpy.data.meshes.new("柱")
        bm.to_mesh(mesh); bm.free(); mesh.update()
        obj = bpy.data.objects.new("柱", mesh)
        obj.location = (lx, ly, lz)
        link_to_named_collection(obj, "柱", context)
        if self.shape == 'CIRCLE':
            for poly in mesh.polygons: poly.use_smooth = True
        if self.auto_material:
            apply_material(obj, "柱_木材", (0.55, 0.35, 0.18, 1.0), "mat_pillar")
        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        context.view_layer.objects.active = obj
        dim_str = f"{self.width}×{self.depth}×{self.height}mm"
        self.report({'INFO'}, f"柱を追加: {dim_str}")
        return {'FINISHED'}

    def invoke(self, context, event):
        props = context.scene.archicad
        if props.snap_enabled:
            cur = context.scene.cursor.location
            snapped = snap_to_grid(Vector(cur), context)
            self.loc = (snapped.x * 1000, snapped.y * 1000, snapped.z * 1000)
        return context.window_manager.invoke_props_dialog(self, width=320)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "shape")
        layout.separator()

        box = layout.box()
        box.label(text="寸法 (mm)", icon='SNAP_INCREMENT')
        box.prop(self, "width")
        if self.shape == 'RECT':
            box.prop(self, "depth")
        else:
            box.prop(self, "segments")
        box.prop(self, "height")

        box2 = layout.box()
        box2.label(text="配置 (mm)", icon='EMPTY_ARROWS')
        row = box2.row()
        row.prop(self, "loc", index=0, text="X")
        row.prop(self, "loc", index=1, text="Y")
        row.prop(self, "loc", index=2, text="Z")

        layout.prop(self, "auto_material")


# ------------------------------------------------------------------ #
#  柱 連続配置 オペレーター
# ------------------------------------------------------------------ #

class ARCHICAD_OT_place_pillars(bpy.types.Operator):
    """グリッド上で柱を連続配置（クリックで配置 / 右クリック・ESC で終了）"""
    bl_idname = "archicad.place_pillars"
    bl_label = "柱を連続配置"
    bl_options = {'REGISTER', 'UNDO'}

    width: FloatProperty(
        name="幅 X (mm)", default=105, min=1, max=10000,
    )
    depth: FloatProperty(
        name="奥行 Y (mm)", default=105, min=1, max=10000,
    )
    height: FloatProperty(
        name="高さ Z (mm)", default=2800, min=1, max=50000,
    )
    shape: EnumProperty(
        name="断面形状",
        items=[('RECT', '角柱', ''), ('CIRCLE', '丸柱', '')],
        default='RECT',
    )
    segments: IntProperty(name="円の分割数", default=32, min=8, max=128)
    auto_material: BoolProperty(name="自動マテリアル", default=True)

    def invoke(self, context, event):
        self._preview = None
        self._count = 0
        snap_hint = "  [SNAP ON]" if context.scene.archicad.snap_enabled else ""
        context.workspace.status_text_set(
            f"クリック: 柱を配置  |  右クリック・ESC: 終了{snap_hint}")
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type == 'MOUSEMOVE':
            pos = self._mouse_to_location(context, event)
            pos = snap_to_grid(pos, context)
            self._update_preview(pos, context)
            if context.area:
                context.area.tag_redraw()

        elif event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            pos = self._mouse_to_location(context, event)
            pos = snap_to_grid(pos, context)
            self._place_one(context, pos)

        elif event.type in {'RIGHTMOUSE', 'ESC'}:
            self._remove_preview(context)
            context.workspace.status_text_set(None)
            return {'FINISHED'} if self._count > 0 else {'CANCELLED'}

        elif event.type in {'UNDO', 'REDO'}:
            self._remove_preview(context)
            context.workspace.status_text_set(None)
            return {'CANCELLED'}

        elif event.type in _NAV_EVENTS:
            return {'PASS_THROUGH'}

        return {'RUNNING_MODAL'}

    # ---- ヘルパー ----

    def _mouse_to_location(self, context, event):
        region = context.region
        rv3d = context.region_data
        coord = (event.mouse_region_x, event.mouse_region_y)
        origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, coord)
        direction = view3d_utils.region_2d_to_vector_3d(region, rv3d, coord)
        z = context.scene.cursor.location.z
        t = (z - origin.z) / direction.z if abs(direction.z) > 1e-6 else 0.0
        return Vector((origin.x + t * direction.x,
                       origin.y + t * direction.y, z))

    def _place_one(self, context, pos):
        bm = _make_pillar_bm(mm(self.width), mm(self.depth), mm(self.height),
                             self.shape, self.segments)
        mesh = bpy.data.meshes.new("柱")
        bm.to_mesh(mesh); bm.free(); mesh.update()
        obj = bpy.data.objects.new("柱", mesh)
        obj.location = pos
        link_to_named_collection(obj, "柱", context)
        if self.shape == 'CIRCLE':
            for poly in mesh.polygons: poly.use_smooth = True
        if self.auto_material:
            apply_material(obj, "柱_木材", (0.55, 0.35, 0.18, 1.0), "mat_pillar")
        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        context.view_layer.objects.active = obj
        self._count += 1

    def _update_preview(self, pos, context):
        if self._preview is None:
            bm = _make_pillar_bm(mm(self.width), mm(self.depth),
                                 mm(self.height), self.shape, self.segments)
            mesh = bpy.data.meshes.new("_pillar_preview")
            bm.to_mesh(mesh); bm.free(); mesh.update()
            self._preview = bpy.data.objects.new("_pillar_preview", mesh)
            self._preview.display_type = 'WIRE'
            context.collection.objects.link(self._preview)
        try:
            self._preview.location = pos
        except (ReferenceError, RuntimeError):
            self._preview = None

    def _remove_preview(self, context):
        if self._preview is not None:
            try:
                mesh = self._preview.data
                bpy.data.objects.remove(self._preview)
                bpy.data.meshes.remove(mesh)
            except (ReferenceError, RuntimeError):
                pass
            self._preview = None

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "shape")
        layout.prop(self, "width")
        if self.shape == 'RECT':
            layout.prop(self, "depth")
        else:
            layout.prop(self, "segments")
        layout.prop(self, "height")
        layout.prop(self, "auto_material")


# ------------------------------------------------------------------ #
#  壁 (Wall) オペレーター
# ------------------------------------------------------------------ #

class ARCHICAD_OT_add_wall(bpy.types.Operator):
    """壁を生成（mm指定）"""
    bl_idname = "archicad.add_wall"
    bl_label = "壁を追加"
    bl_options = {'REGISTER', 'UNDO'}

    length: FloatProperty(
        name="長さ (mm)", default=3640, min=1, max=100000,
        description="壁の長さ（水平方向）mm"
    )
    height: FloatProperty(
        name="高さ (mm)", default=2400, min=1, max=50000,
        description="壁の高さ mm"
    )
    thickness: FloatProperty(
        name="厚み (mm)", default=120, min=1, max=5000,
        description="壁の厚み mm"
    )
    direction: EnumProperty(
        name="方向",
        items=[
            ('X', 'X方向', '壁をX軸に沿って配置'),
            ('Y', 'Y方向', '壁をY軸に沿って配置'),
        ],
        default='X',
    )
    loc: FloatVectorProperty(
        name="始点位置 (mm)",
        default=(0, 0, 0),
        description="壁の始点 X, Y, Z 座標 (mm)",
        size=3,
    )
    auto_material: BoolProperty(
        name="自動マテリアル", default=True,
        description="壁用マテリアルを自動適用"
    )
    wall_type: EnumProperty(
        name="壁タイプ",
        items=[
            ('EXTERIOR', '外壁', '外壁（厚め）'),
            ('INTERIOR', '内壁', '内壁（薄め）'),
            ('PARTITION', '間仕切り', '間仕切り壁'),
        ],
        default='INTERIOR',
    )

    def execute(self, context):
        l = mm(self.length)
        h = mm(self.height)
        t = mm(self.thickness)
        lx, ly, lz = mm(self.loc[0]), mm(self.loc[1]), mm(self.loc[2])

        bm = bmesh.new()

        if self.direction == 'X':
            # X方向に伸びる壁
            verts_bottom = [
                bm.verts.new((0,    -t/2, 0)),
                bm.verts.new((l,    -t/2, 0)),
                bm.verts.new((l,     t/2, 0)),
                bm.verts.new((0,     t/2, 0)),
            ]
            verts_top = [
                bm.verts.new((0,    -t/2, h)),
                bm.verts.new((l,    -t/2, h)),
                bm.verts.new((l,     t/2, h)),
                bm.verts.new((0,     t/2, h)),
            ]
        else:
            # Y方向に伸びる壁
            verts_bottom = [
                bm.verts.new((-t/2, 0,  0)),
                bm.verts.new(( t/2, 0,  0)),
                bm.verts.new(( t/2, l,  0)),
                bm.verts.new((-t/2, l,  0)),
            ]
            verts_top = [
                bm.verts.new((-t/2, 0,  h)),
                bm.verts.new(( t/2, 0,  h)),
                bm.verts.new(( t/2, l,  h)),
                bm.verts.new((-t/2, l,  h)),
            ]

        # 底面・上面
        bm.faces.new(verts_bottom)
        bm.faces.new(verts_top[::-1])
        # 側面
        for i in range(4):
            ni = (i + 1) % 4
            bm.faces.new([
                verts_bottom[i], verts_bottom[ni],
                verts_top[ni], verts_top[i]
            ])

        mesh = bpy.data.meshes.new("壁")
        bm.to_mesh(mesh)
        bm.free()
        mesh.update()

        obj = bpy.data.objects.new("壁", mesh)
        obj.location = (lx, ly, lz)
        link_to_named_collection(obj, "壁", context)

        if self.auto_material:
            colors = {
                'EXTERIOR':  ("外壁",     (0.85, 0.82, 0.78, 1.0), "mat_wall_exterior"),
                'INTERIOR':  ("内壁",     (0.92, 0.91, 0.88, 1.0), "mat_wall_interior"),
                'PARTITION': ("間仕切り", (0.80, 0.85, 0.80, 1.0), "mat_wall_partition"),
            }
            mat_name, color, pref_key = colors[self.wall_type]
            apply_material(obj, f"壁_{mat_name}", color, pref_key)

        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        context.view_layer.objects.active = obj

        dir_label = {'X': 'X方向', 'Y': 'Y方向'}.get(self.direction, self.direction)
        dim_str = f"{self.length}×{self.height}×t{self.thickness}mm"
        self.report({'INFO'}, f"壁を追加: {dim_str} ({dir_label})")
        return {'FINISHED'}

    # 壁タイプごとのデフォルト厚み (mm)
    _DEFAULT_THICKNESS = {'EXTERIOR': 150, 'INTERIOR': 120, 'PARTITION': 70}

    def invoke(self, context, event):
        if self.thickness == 120:
            self.thickness = self._DEFAULT_THICKNESS.get(self.wall_type, 120)
        self._start = None
        self._preview = None
        self._num_str = ""      # 数値入力バッファ
        self._last_mouse = None # 最後のマウス位置（数値確定時の方向決定用）
        self._update_status(context)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type == 'MOUSEMOVE':
            if self._start is not None:
                cur = self._mouse_to_ground(context, event)
                cur = snap_to_grid(cur, context)
                self._last_mouse = cur
                if self._num_str:
                    self._update_preview_numeric(cur)
                else:
                    self._update_preview(cur)
                if context.area:
                    context.area.tag_redraw()

        elif event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            self._num_str = ""  # 数値入力中でもクリック優先
            pos = self._mouse_to_ground(context, event)
            pos = snap_to_grid(pos, context)
            if self._start is None:
                self._start = pos
                self._last_mouse = pos
                self._create_preview(context)
            else:
                self._place_wall_from_points(context, self._start, pos)
                self._start = pos
            self._update_status(context)

        elif event.value == 'PRESS' and event.type in _NUM_KEYS:
            if self._start is not None:
                ch = _NUM_KEYS[event.type]
                if ch == '.' and '.' in self._num_str:
                    pass  # 小数点は一つだけ
                else:
                    self._num_str += ch
                    if self._last_mouse:
                        self._update_preview_numeric(self._last_mouse)
                    if context.area:
                        context.area.tag_redraw()
                self._update_status(context)

        elif event.type == 'BACK_SPACE' and event.value == 'PRESS':
            if self._num_str:
                self._num_str = self._num_str[:-1]
                if self._last_mouse:
                    if self._num_str:
                        self._update_preview_numeric(self._last_mouse)
                    else:
                        self._update_preview(self._last_mouse)
                if context.area:
                    context.area.tag_redraw()
                self._update_status(context)

        elif event.type in {'RET', 'NUMPAD_ENTER'} and event.value == 'PRESS':
            if self._start is not None and self._num_str:
                try:
                    length_mm = float(self._num_str)
                except ValueError:
                    self._num_str = ""
                    self._update_status(context)
                    return {'RUNNING_MODAL'}
                if length_mm >= 1 and self._last_mouse:
                    self._place_wall_numeric(context, length_mm)
                else:
                    self.report({'WARNING'}, "長さが短すぎます")
                self._num_str = ""
                self._update_status(context)

        elif event.type == 'RIGHTMOUSE' and event.value == 'PRESS':
            self._remove_preview(context)
            context.workspace.status_text_set(None)
            return {'FINISHED'}

        elif event.type == 'ESC':
            self._remove_preview(context)
            context.workspace.status_text_set(None)
            return {'CANCELLED'}

        elif event.type in {'UNDO', 'REDO'}:
            self._remove_preview(context)
            context.workspace.status_text_set(None)
            return {'CANCELLED'}

        elif event.type in _NAV_EVENTS:
            return {'PASS_THROUGH'}

        return {'RUNNING_MODAL'}

    # ---- ヘルパー ----

    def _mouse_to_ground(self, context, event):
        """マウス座標を 3Dカーソルの Z 高さの水平面上の点に変換"""
        region = context.region
        rv3d = context.region_data
        coord = (event.mouse_region_x, event.mouse_region_y)
        origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, coord)
        direction = view3d_utils.region_2d_to_vector_3d(region, rv3d, coord)
        z = context.scene.cursor.location.z
        t = (z - origin.z) / direction.z if abs(direction.z) > 1e-6 else 0.0
        return Vector((origin.x + t * direction.x,
                       origin.y + t * direction.y, z))

    def _create_preview(self, context):
        mesh = bpy.data.meshes.new("_wall_preview")
        self._preview = bpy.data.objects.new("_wall_preview", mesh)
        self._preview.display_type = 'WIRE'
        context.collection.objects.link(self._preview)

    def _update_preview(self, end):
        if self._preview is None or self._start is None:
            return
        start = self._start
        h = mm(self.height)
        dx = end.x - start.x
        dy = end.y - start.y

        bm = bmesh.new()
        if abs(dx) >= abs(dy):
            # X方向プレビュー（正面の1面）
            v1 = bm.verts.new((0,  0, 0))
            v2 = bm.verts.new((dx, 0, 0))
            v3 = bm.verts.new((dx, 0, h))
            v4 = bm.verts.new((0,  0, h))
        else:
            # Y方向プレビュー
            v1 = bm.verts.new((0, 0,  0))
            v2 = bm.verts.new((0, dy, 0))
            v3 = bm.verts.new((0, dy, h))
            v4 = bm.verts.new((0, 0,  h))
        bm.faces.new([v1, v2, v3, v4])
        try:
            bm.to_mesh(self._preview.data)
            bm.free()
            self._preview.data.update()
            self._preview.location = start
        except (ReferenceError, RuntimeError):
            bm.free()
            self._preview = None

    def _remove_preview(self, context):
        if self._preview is not None:
            try:
                mesh = self._preview.data
                bpy.data.objects.remove(self._preview)
                bpy.data.meshes.remove(mesh)
            except (ReferenceError, RuntimeError):
                pass
            self._preview = None

    def _place_wall_from_points(self, context, start, end):
        """2点クリックから壁を配置"""
        dx = end.x - start.x
        dy = end.y - start.y
        if abs(dx) >= abs(dy):
            self.direction = 'X'
            self.length = abs(dx) * 1000
            self.loc = (min(start.x, end.x) * 1000,
                        start.y * 1000, start.z * 1000)
        else:
            self.direction = 'Y'
            self.length = abs(dy) * 1000
            self.loc = (start.x * 1000,
                        min(start.y, end.y) * 1000, start.z * 1000)
        if self.length >= 1:
            self.execute(context)
        else:
            self.report({'WARNING'}, "長さが短すぎます")

    def _place_wall_numeric(self, context, length_mm):
        """数値入力した距離で壁を配置し、終点を次の始点にする"""
        start = self._start
        mouse = self._last_mouse
        dx = mouse.x - start.x
        dy = mouse.y - start.y
        length_m = mm(length_mm)
        if abs(dx) >= abs(dy):
            self.direction = 'X'
            self.length = length_mm
            sign = 1.0 if dx >= 0 else -1.0
            end_x = start.x + sign * length_m
            self.loc = (min(start.x, end_x) * 1000,
                        start.y * 1000, start.z * 1000)
            next_start = Vector((end_x, start.y, start.z))
        else:
            self.direction = 'Y'
            self.length = length_mm
            sign = 1.0 if dy >= 0 else -1.0
            end_y = start.y + sign * length_m
            self.loc = (start.x * 1000,
                        min(start.y, end_y) * 1000, start.z * 1000)
            next_start = Vector((start.x, end_y, start.z))
        self.execute(context)
        self._start = next_start
        self._last_mouse = next_start

    def _update_preview_numeric(self, mouse_pos):
        """数値入力中のプレビュー（タイプした長さで表示）"""
        if self._preview is None or self._start is None or not self._num_str:
            return
        try:
            length_mm = float(self._num_str)
        except ValueError:
            return
        start = self._start
        h = mm(self.height)
        dx = mouse_pos.x - start.x
        dy = mouse_pos.y - start.y
        length_m = mm(length_mm)
        bm = bmesh.new()
        if abs(dx) >= abs(dy):
            sign = 1.0 if dx >= 0 else -1.0
            d = sign * length_m
            v1 = bm.verts.new((0, 0, 0)); v2 = bm.verts.new((d, 0, 0))
            v3 = bm.verts.new((d, 0, h)); v4 = bm.verts.new((0, 0, h))
        else:
            sign = 1.0 if dy >= 0 else -1.0
            d = sign * length_m
            v1 = bm.verts.new((0, 0, 0)); v2 = bm.verts.new((0, d, 0))
            v3 = bm.verts.new((0, d, h)); v4 = bm.verts.new((0, 0, h))
        bm.faces.new([v1, v2, v3, v4])
        try:
            bm.to_mesh(self._preview.data)
            bm.free()
            self._preview.data.update()
            self._preview.location = start
        except (ReferenceError, RuntimeError):
            bm.free()
            self._preview = None

    def _update_status(self, context):
        """ステータスバーテキストを状態に応じて更新"""
        snap_hint = "  [SNAP ON]" if context.scene.archicad.snap_enabled else ""
        if self._start is None:
            context.workspace.status_text_set(
                f"クリック: 始点を指定  |  ESC: キャンセル{snap_hint}")
        elif self._num_str:
            context.workspace.status_text_set(
                f"距離: {self._num_str} mm  |  Enter: 確定  |  BS: 修正  |  ESC: キャンセル")
        else:
            context.workspace.status_text_set(
                f"クリック: 次の点  |  数字: 距離入力  |  右クリック: 終了  |  ESC: キャンセル{snap_hint}")

    def draw(self, context):
        """F9 オペレーターパネル用（配置後の調整）"""
        layout = self.layout
        layout.prop(self, "wall_type")
        layout.prop(self, "direction")
        layout.prop(self, "height")
        layout.prop(self, "thickness")
        layout.prop(self, "auto_material")


# ------------------------------------------------------------------ #
#  開口部 (Opening) オペレーター
# ------------------------------------------------------------------ #

class ARCHICAD_OT_add_opening(bpy.types.Operator):
    """選択中の壁に開口部（窓・ドア）を開ける"""
    bl_idname = "archicad.add_opening"
    bl_label = "開口部を追加"
    bl_options = {'REGISTER', 'UNDO'}

    opening_type: EnumProperty(
        name="種類",
        items=[
            ('WINDOW', '窓', '窓用の開口'),
            ('DOOR', 'ドア', 'ドア用の開口'),
        ],
        default='WINDOW',
    )
    width: FloatProperty(
        name="幅 (mm)", default=1650, min=100, max=10000,
        description="開口部の幅 mm"
    )
    op_height: FloatProperty(
        name="高さ (mm)", default=1100, min=100, max=10000,
        description="開口部の高さ mm",
        update=_on_op_height_change,
    )
    sill_height: FloatProperty(
        name="窓台高さ (mm)", default=900, min=0, max=10000,
        description="FL（床面）からの高さ mm",
        update=_on_sill_height_change,
    )
    offset: FloatProperty(
        name="壁始点からの距離 (mm)", default=500, min=0, max=100000,
        description="壁の始点から開口部左端までの距離 mm"
    )
    use_template: BoolProperty(
        name="カスタムオブジェクトを挿入",
        default=False,
        description="開口部にシーン内のオブジェクトをはめ込む",
    )
    template_name: StringProperty(
        name="オブジェクト名",
        default="",
        description="挿入するオブジェクト名（シーン内に存在すること）",
    )
    auto_scale: BoolProperty(
        name="開口に自動フィット",
        default=True,
        description="テンプレートを開口幅・高さに合わせてスケール",
    )
    def execute(self, context):
        obj = context.active_object
        if obj is None or obj.type != 'MESH':
            self.report({'ERROR'}, "壁オブジェクトを選択してください")
            return {'CANCELLED'}

        w    = mm(self.width)
        h    = mm(self.op_height)
        sill = 0.0 if self.opening_type == 'DOOR' else mm(self.sill_height)
        off  = mm(self.offset)
        dims = obj.dimensions   # スケール=1・回転なし前提のワールドサイズ
        EPS  = 0.001            # 壁厚より少し大きくして確実に貫通させる

        # ── カッターボックスの頂点をローカル座標で計算 ──────────────
        if dims.x > dims.y:
            # X方向の壁: 幅はX、厚みはY
            x1, x2 = off, off + w
            z1, z2 = sill, sill + h
            ht = dims.y / 2 + EPS
            pts = [
                (x1, -ht, z1), (x2, -ht, z1), (x2,  ht, z1), (x1,  ht, z1),
                (x1, -ht, z2), (x2, -ht, z2), (x2,  ht, z2), (x1,  ht, z2),
            ]
        else:
            # Y方向の壁: 幅はY、厚みはX
            y1, y2 = off, off + w
            z1, z2 = sill, sill + h
            ht = dims.x / 2 + EPS
            pts = [
                (-ht, y1, z1), (ht, y1, z1), (ht, y2, z1), (-ht, y2, z1),
                (-ht, y1, z2), (ht, y1, z2), (ht, y2, z2), (-ht, y2, z2),
            ]

        # ── カッターメッシュ（閉じたボックス）を bmesh で作成 ────────
        cutter_mesh = bpy.data.meshes.new("_opening_cutter")
        bm = bmesh.new()
        v = [bm.verts.new(p) for p in pts]
        bm.faces.new([v[0], v[1], v[2], v[3]])  # 底面
        bm.faces.new([v[7], v[6], v[5], v[4]])  # 上面
        bm.faces.new([v[0], v[4], v[5], v[1]])  # 背面
        bm.faces.new([v[2], v[6], v[7], v[3]])  # 前面
        bm.faces.new([v[0], v[3], v[7], v[4]])  # 左面
        bm.faces.new([v[1], v[5], v[6], v[2]])  # 右面
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])  # 法線を外向きに統一
        bm.to_mesh(cutter_mesh)
        bm.free()
        cutter_mesh.update()

        # ── カッターオブジェクトを壁と同じ原点に配置してリンク ───────
        cutter_obj = bpy.data.objects.new("開口カッター", cutter_mesh)
        cutter_obj.location = obj.location  # 壁のローカル座標系と一致
        cutter_obj.display_type = 'WIRE'    # ワイヤー表示
        cutter_obj.hide_render = True       # レンダリングから除外
        cutter_obj.hide_viewport = False    # ブーリアンが参照できるよう表示を維持
        link_to_named_collection(cutter_obj, "開口カッター", context)

        # ── ビューレイヤーを更新してカッターを確実に認識させる ────────
        context.view_layer.update()

        # ── Boolean DIFFERENCE モディファイアを追加（適用せず残す）──
        mod = obj.modifiers.new("開口部ブーリアン", 'BOOLEAN')
        mod.operation = 'DIFFERENCE'
        mod.solver    = 'EXACT'
        mod.object    = cutter_obj
        mod.use_self  = False

        # ── カスタムオブジェクト挿入 ──────────────────────────────────
        if self.use_template and self.template_name:
            template = bpy.data.objects.get(self.template_name)
            if template is None:
                self.report({'WARNING'},
                    f"テンプレート '{self.template_name}' が見つかりません")
            else:
                # X壁: 面法線 ±Y → 回転不要 / Y壁: 面法線 ±X → Z軸 90°回転
                if dims.x > dims.y:
                    local_center = Vector((off + w / 2, 0.0, sill + h / 2))
                    rot_z = 0.0
                else:
                    local_center = Vector((0.0, off + w / 2, sill + h / 2))
                    rot_z = math.pi / 2

                world_center = obj.matrix_world @ local_center
                new_obj = template.copy()
                link_to_named_collection(new_obj, "開口部", context)
                new_obj.location = world_center
                new_obj.rotation_euler = (0.0, 0.0, rot_z)

                if self.auto_scale:
                    tdx = template.dimensions.x
                    tdz = template.dimensions.z
                    if tdx > 1e-6 and tdz > 1e-6:
                        new_obj.scale = (w / tdx, w / tdx, h / tdz)
                    else:
                        self.report({'WARNING'},
                            "テンプレートの寸法がゼロのためスケール適用をスキップ")
        # ─────────────────────────────────────────────────────────────

        self.report({'INFO'},
            f"開口部を追加: {self.width}×{self.op_height}mm "
            f"(FL+{self.sill_height}mm)")
        return {'FINISHED'}

    def invoke(self, context, event):
        if self.opening_type == 'DOOR':
            self.op_height = 2000
            self.sill_height = 0
            self.width = 800
        return context.window_manager.invoke_props_dialog(self, width=320)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "opening_type")
        layout.separator()

        box = layout.box()
        box.label(text="寸法 (mm)", icon='SNAP_INCREMENT')
        box.prop(self, "width")
        box.prop(self, "op_height")
        if self.opening_type == 'WINDOW':
            box.prop(self, "sill_height")

        box2 = layout.box()
        box2.label(text="位置 (mm)", icon='EMPTY_ARROWS')
        box2.prop(self, "offset")

        box3 = layout.box()
        box3.prop(self, "use_template", icon='OBJECT_DATA', toggle=True)
        if self.use_template:
            box3.prop_search(self, "template_name",
                             context.scene, "objects", text="オブジェクト")
            box3.prop(self, "auto_scale")


# ------------------------------------------------------------------ #
#  床 (Floor) オペレーター
# ------------------------------------------------------------------ #

class ARCHICAD_OT_add_floor(bpy.types.Operator):
    """床スラブを生成（mm指定）"""
    bl_idname = "archicad.add_floor"
    bl_label = "床を追加"
    bl_options = {'REGISTER', 'UNDO'}

    length: FloatProperty(
        name="長さ X (mm)", default=3640, min=1, max=100000,
        description="床の長さ（X方向）mm"
    )
    width: FloatProperty(
        name="奥行 Y (mm)", default=2730, min=1, max=100000,
        description="床の奥行（Y方向）mm"
    )
    thickness: FloatProperty(
        name="厚み (mm)", default=150, min=1, max=2000,
        description="床スラブの厚み mm"
    )
    loc: FloatVectorProperty(
        name="配置位置 (mm)",
        default=(0, 0, 0),
        description="床の角（X-, Y-）の X, Y, Z 座標 (mm)",
        size=3,
    )
    floor_type: EnumProperty(
        name="床タイプ",
        items=[
            ('CONCRETE', 'コンクリート', 'RC床スラブ'),
            ('WOOD',     '木床',         '木造床（根太・合板）'),
        ],
        default='CONCRETE',
    )
    auto_material: BoolProperty(
        name="自動マテリアル", default=True,
        description="床用マテリアルを自動適用"
    )

    def execute(self, context):
        lx = mm(self.length)
        ly = mm(self.width)
        t  = mm(self.thickness)
        ox, oy, oz = mm(self.loc[0]), mm(self.loc[1]), mm(self.loc[2])

        bm = bmesh.new()

        verts_bottom = [
            bm.verts.new((0,  0,  -t)),
            bm.verts.new((lx, 0,  -t)),
            bm.verts.new((lx, ly, -t)),
            bm.verts.new((0,  ly, -t)),
        ]
        verts_top = [
            bm.verts.new((0,  0,  0)),
            bm.verts.new((lx, 0,  0)),
            bm.verts.new((lx, ly, 0)),
            bm.verts.new((0,  ly, 0)),
        ]

        bm.faces.new(verts_bottom)
        bm.faces.new(verts_top[::-1])
        for i in range(4):
            ni = (i + 1) % 4
            bm.faces.new([
                verts_bottom[i], verts_bottom[ni],
                verts_top[ni],   verts_top[i],
            ])

        mesh = bpy.data.meshes.new("床")
        bm.to_mesh(mesh)
        bm.free()
        mesh.update()

        obj = bpy.data.objects.new("床", mesh)
        obj.location = (ox, oy, oz)
        link_to_named_collection(obj, "床", context)

        if self.auto_material:
            colors = {
                'CONCRETE': ("床_コンクリート", (0.60, 0.60, 0.60, 1.0), "mat_floor_concrete"),
                'WOOD':     ("床_木",           (0.55, 0.38, 0.20, 1.0), "mat_floor_wood"),
            }
            mat_name, color, pref_key = colors[self.floor_type]
            apply_material(obj, mat_name, color, pref_key)

        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        context.view_layer.objects.active = obj

        self.report({'INFO'},
            f"床を追加: {self.length}×{self.width}×t{self.thickness}mm")
        return {'FINISHED'}

    def invoke(self, context, event):
        self._start = None
        self._preview = None
        snap_hint = "  [SNAP ON]" if context.scene.archicad.snap_enabled else ""
        context.workspace.status_text_set(
            f"クリック: 始点を指定  |  ESC: キャンセル{snap_hint}")
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type == 'MOUSEMOVE':
            if self._start is not None:
                cur = self._mouse_to_floor(context, event)
                cur = snap_to_grid(cur, context)
                self._update_preview(cur)
                if context.area:
                    context.area.tag_redraw()

        elif event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            pos = self._mouse_to_floor(context, event)
            pos = snap_to_grid(pos, context)
            if self._start is None:
                self._start = pos
                self._create_preview(context)
                context.workspace.status_text_set(
                    "クリック: 終点を指定  |  ESC: キャンセル")
            else:
                self._remove_preview(context)
                context.workspace.status_text_set(None)

                start, end = self._start, pos
                sx = min(start.x, end.x)
                sy = min(start.y, end.y)
                self.loc = (sx * 1000, sy * 1000, start.z * 1000)
                self.length = abs(end.x - start.x) * 1000
                self.width  = abs(end.y - start.y) * 1000

                if self.length < 1 or self.width < 1:
                    self.report({'WARNING'}, "面積が小さすぎます")
                    return {'CANCELLED'}
                return self.execute(context)

        elif event.type in {'RIGHTMOUSE', 'ESC'}:
            self._remove_preview(context)
            context.workspace.status_text_set(None)
            return {'CANCELLED'}

        elif event.type in {'UNDO', 'REDO'}:
            self._remove_preview(context)
            context.workspace.status_text_set(None)
            return {'CANCELLED'}

        elif event.type in _NAV_EVENTS:
            return {'PASS_THROUGH'}

        return {'RUNNING_MODAL'}

    # ---- ヘルパー ----

    def _mouse_to_floor(self, context, event):
        """マウス座標を 3Dカーソルの Z 高さの水平面上の点に変換"""
        region = context.region
        rv3d = context.region_data
        coord = (event.mouse_region_x, event.mouse_region_y)
        origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, coord)
        direction = view3d_utils.region_2d_to_vector_3d(region, rv3d, coord)
        z = context.scene.cursor.location.z
        t = (z - origin.z) / direction.z if abs(direction.z) > 1e-6 else 0.0
        return Vector((origin.x + t * direction.x,
                       origin.y + t * direction.y, z))

    def _create_preview(self, context):
        mesh = bpy.data.meshes.new("_floor_preview")
        self._preview = bpy.data.objects.new("_floor_preview", mesh)
        self._preview.display_type = 'WIRE'
        context.collection.objects.link(self._preview)

    def _update_preview(self, end):
        if self._preview is None or self._start is None:
            return
        start = self._start
        dx = end.x - start.x
        dy = end.y - start.y
        bm = bmesh.new()
        verts = [
            bm.verts.new((0,  0,  0)),
            bm.verts.new((dx, 0,  0)),
            bm.verts.new((dx, dy, 0)),
            bm.verts.new((0,  dy, 0)),
        ]
        bm.faces.new(verts)
        try:
            bm.to_mesh(self._preview.data)
            bm.free()
            self._preview.data.update()
            self._preview.location = start
        except (ReferenceError, RuntimeError):
            bm.free()
            self._preview = None

    def _remove_preview(self, context):
        if self._preview is not None:
            try:
                mesh = self._preview.data
                bpy.data.objects.remove(self._preview)
                bpy.data.meshes.remove(mesh)
            except (ReferenceError, RuntimeError):
                pass
            self._preview = None

    def draw(self, context):
        """F9 オペレーターパネル用（配置後の調整）"""
        layout = self.layout
        layout.prop(self, "floor_type")
        layout.prop(self, "thickness")
        layout.prop(self, "auto_material")


# ------------------------------------------------------------------ #
#  グリッド生成（モジュール線）
# ------------------------------------------------------------------ #

class ARCHICAD_OT_add_grid(bpy.types.Operator):
    """建築用通り芯（グリッド線）を生成"""
    bl_idname = "archicad.add_grid"
    bl_label = "通り芯を追加"
    bl_options = {'REGISTER', 'UNDO'}

    span_x: FloatProperty(
        name="X方向スパン (mm)", default=910, min=100, max=100000,
    )
    count_x: IntProperty(
        name="X方向 本数", default=4, min=2, max=50,
    )
    span_y: FloatProperty(
        name="Y方向スパン (mm)", default=910, min=100, max=100000,
    )
    count_y: IntProperty(
        name="Y方向 本数", default=3, min=2, max=50,
    )

    def execute(self, context):
        sx = mm(self.span_x)
        sy = mm(self.span_y)

        # グリッドスナップ用にスパンをシーンプロパティへ保存
        context.scene.archicad.snap_span_x = self.span_x
        context.scene.archicad.snap_span_y = self.span_y

        total_x = sx * (self.count_x - 1)
        total_y = sy * (self.count_y - 1)

        # 通り芯用のコレクション
        col_name = "通り芯"
        if col_name not in bpy.data.collections:
            col = bpy.data.collections.new(col_name)
            context.scene.collection.children.link(col)
        else:
            col = bpy.data.collections[col_name]

        # X方向の通り芯（Y軸に平行な線）
        labels_x = "XYZWVUTSRQPONMLKJIHGFEDCBA"
        for i in range(self.count_x):
            x_pos = sx * i
            mesh = bpy.data.meshes.new(f"通り芯_X{i}")
            bm = bmesh.new()
            v1 = bm.verts.new((x_pos, -mm(1000), 0))
            v2 = bm.verts.new((x_pos, total_y + mm(1000), 0))
            bm.edges.new([v1, v2])
            bm.to_mesh(mesh)
            bm.free()

            obj = bpy.data.objects.new(f"X{i+1}", mesh)
            obj.display_type = 'WIRE'
            col.objects.link(obj)

            # テキストラベル
            label = labels_x[i] if i < len(labels_x) else f"X{i+1}"
            bpy.ops.object.text_add(location=(x_pos, -mm(1500), 0))
            txt_obj = context.active_object
            txt_obj.data.body = label
            txt_obj.data.size = mm(300)
            txt_obj.name = f"ラベル_{label}"
            txt_obj.rotation_euler = (math.pi/2, 0, 0)

            # コレクションに移動
            for c in txt_obj.users_collection:
                c.objects.unlink(txt_obj)
            col.objects.link(txt_obj)

        # Y方向の通り芯（X軸に平行な線）
        for i in range(self.count_y):
            y_pos = sy * i
            mesh = bpy.data.meshes.new(f"通り芯_Y{i}")
            bm = bmesh.new()
            v1 = bm.verts.new((-mm(1000), y_pos, 0))
            v2 = bm.verts.new((total_x + mm(1000), y_pos, 0))
            bm.edges.new([v1, v2])
            bm.to_mesh(mesh)
            bm.free()

            obj = bpy.data.objects.new(f"Y{i+1}", mesh)
            obj.display_type = 'WIRE'
            col.objects.link(obj)

            # 数字ラベル
            bpy.ops.object.text_add(location=(-mm(1500), y_pos, 0))
            txt_obj = context.active_object
            txt_obj.data.body = str(i + 1)
            txt_obj.data.size = mm(300)
            txt_obj.name = f"ラベル_{i+1}"
            txt_obj.rotation_euler = (math.pi/2, 0, 0)

            for c in txt_obj.users_collection:
                c.objects.unlink(txt_obj)
            col.objects.link(txt_obj)

        self.report({'INFO'},
            f"通り芯: X {self.count_x}本(span {self.span_x}mm)"
            f" × Y {self.count_y}本(span {self.span_y}mm)")
        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=320)

    def draw(self, context):
        layout = self.layout
        box = layout.box()
        box.label(text="X方向（通り芯 X,Y,Z...）", icon='EVENT_X')
        box.prop(self, "span_x")
        box.prop(self, "count_x")

        box2 = layout.box()
        box2.label(text="Y方向（通り芯 1,2,3...）", icon='EVENT_Y')
        box2.prop(self, "span_y")
        box2.prop(self, "count_y")


# ------------------------------------------------------------------ #
#  サイドバーパネル
# ------------------------------------------------------------------ #

class ARCHICAD_PT_main_panel(bpy.types.Panel):
    bl_label = "Archi CAD Tools"
    bl_idname = "ARCHICAD_PT_main"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Archi CAD"

    def draw(self, context):
        layout = self.layout

        # 通り芯
        box = layout.box()
        box.label(text="基準", icon='MESH_GRID')
        box.operator("archicad.add_grid", text="通り芯", icon='MESH_GRID')

        # グリッドスナップ
        box_snap = layout.box()
        scene_props = context.scene.archicad
        row = box_snap.row()
        row.label(text="グリッドスナップ", icon='SNAP_ON')
        row.prop(scene_props, "snap_enabled", text="")
        if scene_props.snap_enabled:
            sub = box_snap.column(align=True)
            sub.prop(scene_props, "snap_span_x", text="X (mm)")
            sub.prop(scene_props, "snap_span_y", text="Y (mm)")

        # 構造
        box2 = layout.box()
        box2.label(text="構造要素", icon='MESH_CUBE')
        row_p = box2.row(align=True)
        row_p.operator("archicad.add_pillar",    text="柱",    icon='MESH_CUBE')
        row_p.operator("archicad.place_pillars", text="連続配置", icon='SNAP_ON')
        box2.operator("archicad.add_wall",   text="壁", icon='MOD_SOLIDIFY')
        box2.operator("archicad.add_floor",  text="床", icon='MESH_PLANE')

        # 開口部
        box3 = layout.box()
        box3.label(text="開口部", icon='FULLSCREEN_EXIT')
        row = box3.row(align=True)
        op_win = row.operator("archicad.add_opening", text="窓", icon='FULLSCREEN_EXIT')
        op_win.opening_type = 'WINDOW'
        op_door = row.operator("archicad.add_opening", text="ドア", icon='ARMATURE_DATA')
        op_door.opening_type = 'DOOR'

        # 情報
        obj = context.active_object
        if obj and obj.type == 'MESH':
            box4 = layout.box()
            box4.label(text="選択中", icon='INFO')
            box4.label(text=f"名前: {obj.name}")
            d = obj.dimensions
            box4.label(text=f"寸法: {d.x*1000:.0f}×{d.y*1000:.0f}×{d.z*1000:.0f} mm")
            loc = obj.location
            box4.label(text=f"位置: ({loc.x*1000:.0f}, {loc.y*1000:.0f}, {loc.z*1000:.0f}) mm")


# ------------------------------------------------------------------ #
#  アドオン設定（デフォルトマテリアル）
# ------------------------------------------------------------------ #

class ARCHICAD_Preferences(bpy.types.AddonPreferences):
    bl_idname = __name__

    mat_pillar:         StringProperty(name="柱",               default="")
    mat_wall_exterior:  StringProperty(name="外壁",             default="")
    mat_wall_interior:  StringProperty(name="内壁",             default="")
    mat_wall_partition: StringProperty(name="間仕切り壁",       default="")
    mat_floor_concrete: StringProperty(name="床（コンクリート）", default="")
    mat_floor_wood:     StringProperty(name="床（木）",         default="")

    def draw(self, context):
        layout = self.layout
        layout.label(
            text="デフォルトマテリアル（空欄 = 組み込みデフォルトを使用）",
            icon='MATERIAL')
        layout.label(text="※ シーン内に存在するマテリアル名を指定してください")
        col = layout.column(align=True)
        col.prop_search(self, "mat_pillar",         bpy.data, "materials")
        col.prop_search(self, "mat_wall_exterior",  bpy.data, "materials")
        col.prop_search(self, "mat_wall_interior",  bpy.data, "materials")
        col.prop_search(self, "mat_wall_partition", bpy.data, "materials")
        col.prop_search(self, "mat_floor_concrete", bpy.data, "materials")
        col.prop_search(self, "mat_floor_wood",     bpy.data, "materials")


# ------------------------------------------------------------------ #
#  登録
# ------------------------------------------------------------------ #

classes = [
    ARCHICAD_Preferences,
    ARCHICAD_SceneProps,
    ARCHICAD_OT_add_pillar,
    ARCHICAD_OT_place_pillars,
    ARCHICAD_OT_add_wall,
    ARCHICAD_OT_add_floor,
    ARCHICAD_OT_add_opening,
    ARCHICAD_OT_add_grid,
    ARCHICAD_PT_main_panel,
]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.archicad = PointerProperty(type=ARCHICAD_SceneProps)


def unregister():
    del bpy.types.Scene.archicad
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
