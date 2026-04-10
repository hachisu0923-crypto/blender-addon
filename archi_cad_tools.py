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
        w = mm(self.width)
        d = mm(self.depth)
        h = mm(self.height)
        lx, ly, lz = mm(self.loc[0]), mm(self.loc[1]), mm(self.loc[2])

        bm = bmesh.new()

        if self.shape == 'RECT':
            # 角柱
            verts_bottom = [
                bm.verts.new((-w/2, -d/2, 0)),
                bm.verts.new(( w/2, -d/2, 0)),
                bm.verts.new(( w/2,  d/2, 0)),
                bm.verts.new((-w/2,  d/2, 0)),
            ]
            verts_top = [
                bm.verts.new((-w/2, -d/2, h)),
                bm.verts.new(( w/2, -d/2, h)),
                bm.verts.new(( w/2,  d/2, h)),
                bm.verts.new((-w/2,  d/2, h)),
            ]
            # 底面
            bm.faces.new(verts_bottom)
            # 上面
            bm.faces.new(verts_top[::-1])
            # 側面
            for i in range(4):
                ni = (i + 1) % 4
                bm.faces.new([
                    verts_bottom[i], verts_bottom[ni],
                    verts_top[ni], verts_top[i]
                ])
        else:
            # 丸柱
            r = w / 2  # 幅を直径として使用
            verts_bottom = []
            verts_top = []
            for i in range(self.segments):
                angle = 2 * math.pi * i / self.segments
                x = r * math.cos(angle)
                y = r * math.sin(angle)
                verts_bottom.append(bm.verts.new((x, y, 0)))
                verts_top.append(bm.verts.new((x, y, h)))
            bm.faces.new(verts_bottom)
            bm.faces.new(verts_top[::-1])
            for i in range(self.segments):
                ni = (i + 1) % self.segments
                bm.faces.new([
                    verts_bottom[i], verts_bottom[ni],
                    verts_top[ni], verts_top[i]
                ])

        mesh = bpy.data.meshes.new("柱")
        bm.to_mesh(mesh)
        bm.free()
        mesh.update()

        obj = bpy.data.objects.new("柱", mesh)
        obj.location = (lx, ly, lz)
        context.collection.objects.link(obj)

        # スムーズシェード（丸柱のみ）
        if self.shape == 'CIRCLE':
            for poly in mesh.polygons:
                poly.use_smooth = True

        if self.auto_material:
            apply_material(obj, "柱_木材", (0.55, 0.35, 0.18, 1.0), "mat_pillar")

        # 選択状態にする
        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        context.view_layer.objects.active = obj

        dim_str = f"{self.width}×{self.depth}×{self.height}mm"
        self.report({'INFO'}, f"柱を追加: {dim_str}")
        return {'FINISHED'}

    def invoke(self, context, event):
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
        context.collection.objects.link(obj)

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
        context.workspace.status_text_set(
            "クリック: 始点を指定  |  ESC: キャンセル")
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type == 'MOUSEMOVE':
            if self._start is not None:
                cur = self._mouse_to_ground(context, event)
                self._update_preview(cur)
                context.area.tag_redraw()

        elif event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            pos = self._mouse_to_ground(context, event)
            if self._start is None:
                # 始点を確定してプレビュー開始
                self._start = pos
                self._create_preview(context)
                context.workspace.status_text_set(
                    "クリック: 次の点  |  右クリック: 終了  |  ESC: キャンセル")
            else:
                # 壁を配置
                start, end = self._start, pos
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

                # 終点を次の始点にして連続配置を継続
                self._start = pos

        elif event.type == 'RIGHTMOUSE' and event.value == 'PRESS':
            # 右クリックで終了（配置済みの壁は残る）
            self._remove_preview(context)
            context.workspace.status_text_set(None)
            return {'FINISHED'}

        elif event.type == 'ESC':
            # ESC でキャンセル
            self._remove_preview(context)
            context.workspace.status_text_set(None)
            return {'CANCELLED'}

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
        bm.to_mesh(self._preview.data)
        bm.free()
        self._preview.data.update()
        self._preview.location = start

    def _remove_preview(self, context):
        if self._preview is not None:
            mesh = self._preview.data
            bpy.data.objects.remove(self._preview)
            bpy.data.meshes.remove(mesh)
            self._preview = None

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

        w = mm(self.width)
        h = mm(self.op_height)
        sill = mm(self.sill_height)
        off = mm(self.offset)

        if self.opening_type == 'DOOR':
            sill = 0  # ドアはFL=0

        # オブジェクトのバウンディングボックスから壁の向きを推定
        dims = obj.dimensions
        
        bpy.ops.object.mode_set(mode='EDIT')
        bm = bmesh.from_edit_mesh(obj.data)

        # 壁の方向を判定（X方向かY方向か）
        if dims.x > dims.y:
            # X方向の壁
            x1, x2 = off, off + w
            z1, z2 = sill, sill + h

            _bisect(bm, (x1, 0, 0), (1, 0, 0))  # 左辺カット
            _bisect(bm, (x2, 0, 0), (1, 0, 0))  # 右辺カット
            _bisect(bm, (0, 0, z1), (0, 0, 1))  # 下辺カット
            _bisect(bm, (0, 0, z2), (0, 0, 1))  # 上辺カット

            # 開口部範囲内で法線がY方向（壁面）の面を削除
            faces_to_delete = [
                f for f in bm.faces
                if (x1 < f.calc_center_median().x < x2
                    and z1 < f.calc_center_median().z < z2
                    and abs(f.normal.y) > 0.5)
            ]

        else:
            # Y方向の壁
            y1, y2 = off, off + w
            z1, z2 = sill, sill + h

            _bisect(bm, (0, y1, 0), (0, 1, 0))  # 左辺カット
            _bisect(bm, (0, y2, 0), (0, 1, 0))  # 右辺カット
            _bisect(bm, (0, 0, z1), (0, 0, 1))  # 下辺カット
            _bisect(bm, (0, 0, z2), (0, 0, 1))  # 上辺カット

            # 開口部範囲内で法線がX方向（壁面）の面を削除
            faces_to_delete = [
                f for f in bm.faces
                if (y1 < f.calc_center_median().y < y2
                    and z1 < f.calc_center_median().z < z2
                    and abs(f.normal.x) > 0.5)
            ]

        bmesh.ops.delete(bm, geom=faces_to_delete, context='FACES')

        bmesh.update_edit_mesh(obj.data)
        bpy.ops.object.mode_set(mode='OBJECT')

        # ── カスタムオブジェクト挿入 ──────────────────────────────────
        if self.use_template and self.template_name:
            template = bpy.data.objects.get(self.template_name)
            if template is None:
                self.report({'WARNING'},
                    f"テンプレート '{self.template_name}' が見つかりません")
            else:
                # テンプレートは +Y 向き（正面が +Y 方向）で作成すること
                # X壁: 面法線 ±Y → 回転不要
                # Y壁: 面法線 ±X → Z軸 90°回転
                if dims.x > dims.y:
                    local_center = Vector((off + w / 2, 0.0, sill + h / 2))
                    rot_z = 0.0
                else:
                    local_center = Vector((0.0, off + w / 2, sill + h / 2))
                    rot_z = math.pi / 2

                world_center = obj.matrix_world @ local_center

                new_obj = template.copy()   # メッシュデータを共有するコピー
                context.collection.objects.link(new_obj)
                new_obj.location = world_center
                new_obj.rotation_euler = (0.0, 0.0, rot_z)

                if self.auto_scale:
                    tdx = template.dimensions.x
                    tdz = template.dimensions.z
                    if tdx > 1e-6 and tdz > 1e-6:
                        scale_w = w / tdx
                        scale_h = h / tdz
                        new_obj.scale = (scale_w, scale_w, scale_h)
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
        context.collection.objects.link(obj)

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
        context.workspace.status_text_set(
            "クリック: 始点を指定  |  ESC: キャンセル")
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type == 'MOUSEMOVE':
            if self._start is not None:
                cur = self._mouse_to_floor(context, event)
                self._update_preview(cur)
                context.area.tag_redraw()

        elif event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            pos = self._mouse_to_floor(context, event)
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
        bm.to_mesh(self._preview.data)
        bm.free()
        self._preview.data.update()
        self._preview.location = start

    def _remove_preview(self, context):
        if self._preview is not None:
            mesh = self._preview.data
            bpy.data.objects.remove(self._preview)
            bpy.data.meshes.remove(mesh)
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
        name="X方向スパン (mm)", default=3640, min=100, max=100000,
    )
    count_x: IntProperty(
        name="X方向 本数", default=4, min=2, max=50,
    )
    span_y: FloatProperty(
        name="Y方向スパン (mm)", default=2730, min=100, max=100000,
    )
    count_y: IntProperty(
        name="Y方向 本数", default=3, min=2, max=50,
    )

    def execute(self, context):
        sx = mm(self.span_x)
        sy = mm(self.span_y)

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

        # 構造
        box2 = layout.box()
        box2.label(text="構造要素", icon='MESH_CUBE')
        box2.operator("archicad.add_pillar", text="柱", icon='MESH_CUBE')
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
    ARCHICAD_OT_add_pillar,
    ARCHICAD_OT_add_wall,
    ARCHICAD_OT_add_floor,
    ARCHICAD_OT_add_opening,
    ARCHICAD_OT_add_grid,
    ARCHICAD_PT_main_panel,
]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
