# ============================================================
#  Archi BIM Manager — Blender Add-on
#  SQLiteデータベースを使ったBIM情報管理システム
#  Blender 4.x 対応
#  ※ Archi CAD Tools アドオンと併用可能
# ============================================================

bl_info = {
    "name": "Archi BIM Manager",
    "author": "Kenshin Design Office",
    "version": (1, 0, 0),
    "blender": (4, 0, 0),
    "location": "3D Viewport > Sidebar > BIM  /  Properties > Object > BIM",
    "description": "SQLiteデータベースを使ったBIM情報管理（材料・数量・コスト・レポート）",
    "category": "Mesh",
}

import bpy
import sqlite3
import os
import csv
from collections import defaultdict
from bpy.props import (
    FloatProperty, IntProperty, EnumProperty,
    BoolProperty, StringProperty, PointerProperty,
)
from bpy.types import PropertyGroup, Operator, Panel, AddonPreferences


# ------------------------------------------------------------------ #
#  データベースパス
# ------------------------------------------------------------------ #

def get_db_path():
    """SQLiteデータベースのパスを返す。.blendファイルと同じフォルダ、未保存時はホーム。"""
    prefs = bpy.context.preferences.addons.get(__name__)
    if prefs and prefs.preferences.db_path:
        return bpy.path.abspath(prefs.preferences.db_path)
    if bpy.data.filepath:
        return os.path.join(os.path.dirname(bpy.data.filepath), "bim_database.db")
    return os.path.join(os.path.expanduser("~"), "bim_database.db")


# ------------------------------------------------------------------ #
#  データベース操作
# ------------------------------------------------------------------ #

def db_connect():
    return sqlite3.connect(get_db_path())


def db_init():
    """データベースとテーブルを初期化（初回・再初期化）"""
    conn = db_connect()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS materials (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT    NOT NULL UNIQUE,
            category    TEXT    DEFAULT '',
            unit        TEXT    DEFAULT 'm²',
            unit_cost   REAL    DEFAULT 0.0,
            description TEXT    DEFAULT ''
        )
    """)

    # デフォルト材料（INSERT OR IGNORE で重複しない）
    defaults = [
        ('コンクリート（普通）',   '構造',   'm³',  45000, 'RC造スラブ・壁用'),
        ('コンクリート（高強度）', '構造',   'm³',  65000, '高層RC造用'),
        ('構造用集成材',           '構造',   'm³',  90000, '柱・梁用木質材'),
        ('構造用製材',             '構造',   'm³',  70000, '在来軸組用'),
        ('鉄筋（SD295A）',        '構造',   'kg',    120, '一般RC配筋'),
        ('H形鋼',                  '構造',   'kg',    200, '鉄骨梁・柱'),
        ('石膏ボード 12.5mm',      '内装',   'm²',    700, '壁・天井下地'),
        ('石膏ボード 9.5mm',       '内装',   'm²',    600, '天井・軽量下地'),
        ('フローリング（無垢）',   '内装',   'm²',   8500, '無垢木製床材'),
        ('フローリング（複合）',   '内装',   'm²',   4500, '複合フローリング'),
        ('タイル（磁器質）',       '内装',   'm²',   6000, '浴室・玄関'),
        ('クロス（ビニル）',       '内装',   'm²',    900, '一般内装壁紙'),
        ('塗装（EP）',             '内装',   'm²',   1200, 'エマルションペイント'),
        ('グラスウール 100mm',     '断熱',   'm²',   1800, '壁・屋根断熱'),
        ('硬質ウレタン 50mm',      '断熱',   'm²',   3200, '外張り断熱'),
        ('外壁サイディング',       '外装',   'm²',   5500, '窯業系16mm'),
        ('ALCパネル',              '外装',   'm²',   7500, '外壁ALCパネル'),
        ('スレート屋根',           '外装',   'm²',   4500, '化粧スレート'),
        ('金属屋根',               '外装',   'm²',   6000, 'ガルバリウム鋼板'),
        ('アルミサッシ（複層）',   '開口部', '個', 55000, '複層ガラスアルミサッシ'),
        ('木製サッシ（断熱）',     '開口部', '個', 90000, 'LowE複層ガラス'),
        ('フラッシュドア',         '開口部', '個', 30000, '内部ドア（片開き）'),
        ('玄関ドア（断熱）',       '開口部', '個',120000, '断熱玄関ドア'),
        ('防水工事（ウレタン）',   '防水',   'm²',   6000, '屋上・バルコニー'),
        ('防水工事（シート）',     '防水',   'm²',   5000, 'ポリオレフィン系'),
    ]

    for row in defaults:
        cur.execute(
            "INSERT OR IGNORE INTO materials (name, category, unit, unit_cost, description) VALUES (?,?,?,?,?)",
            row
        )

    conn.commit()
    conn.close()


def db_get_materials():
    conn = db_connect()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, name, category, unit, unit_cost, description FROM materials ORDER BY category, name"
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def db_get_material(mat_id):
    conn = db_connect()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, name, category, unit, unit_cost, description FROM materials WHERE id=?",
        (mat_id,)
    )
    row = cur.fetchone()
    conn.close()
    return row


def db_add_material(name, category, unit, unit_cost, description):
    conn = db_connect()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO materials (name, category, unit, unit_cost, description) VALUES (?,?,?,?,?)",
            (name, category, unit, unit_cost, description)
        )
        conn.commit()
        new_id = cur.lastrowid
    except sqlite3.IntegrityError:
        new_id = -1
    conn.close()
    return new_id


def db_update_material(mat_id, name, category, unit, unit_cost, description):
    conn = db_connect()
    cur = conn.cursor()
    cur.execute(
        "UPDATE materials SET name=?, category=?, unit=?, unit_cost=?, description=? WHERE id=?",
        (name, category, unit, unit_cost, description, mat_id)
    )
    conn.commit()
    conn.close()


def db_delete_material(mat_id):
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("DELETE FROM materials WHERE id=?", (mat_id,))
    conn.commit()
    conn.close()


def db_exists():
    return os.path.exists(get_db_path())


# ------------------------------------------------------------------ #
#  BIM要素 プロパティ定義
# ------------------------------------------------------------------ #

ELEMENT_TYPES = [
    ('WALL',      '壁',       '壁要素（外壁・内壁・間仕切り）'),
    ('FLOOR',     '床',       '床スラブ・フローリング'),
    ('PILLAR',    '柱',       '柱要素（角柱・丸柱）'),
    ('BEAM',      '梁',       '梁要素'),
    ('ROOF',      '屋根',     '屋根スラブ・屋根材'),
    ('WINDOW',    '窓',       '窓開口部'),
    ('DOOR',      'ドア',     'ドア開口部'),
    ('STAIR',     '階段',     '階段要素'),
    ('FOUNDATION','基礎',     '基礎・杭'),
    ('OTHER',     'その他',   'その他の建築要素'),
    ('NONE',      '未設定',   'BIM要素として未設定'),
]

FLOOR_LEVELS = [
    ('B3F', 'B3F', '地下3階'),
    ('B2F', 'B2F', '地下2階'),
    ('B1F', 'B1F', '地下1階'),
    ('1F',  '1F',  '1階'),
    ('2F',  '2F',  '2階'),
    ('3F',  '3F',  '3階'),
    ('4F',  '4F',  '4階'),
    ('5F',  '5F',  '5階'),
    ('RF',  'RF',  '屋上'),
]

CONSTRUCTION_PHASES = [
    ('DESIGN',       '設計',   '基本・実施設計'),
    ('PLAN',         '計画',   '施工計画'),
    ('CONSTRUCTION', '施工',   '施工中'),
    ('INSPECT',      '検査',   '完了検査'),
    ('COMPLETE',     '完了',   '引渡し完了'),
]

QUANTITY_UNITS = [
    ('m²', 'm²', '平方メートル'),
    ('m³', 'm³', '立方メートル'),
    ('m',  'm',  'メートル'),
    ('個', '個', '個数'),
    ('式', '式', '一式'),
    ('kg', 'kg', 'キログラム'),
]


class BIM_ElementProps(PropertyGroup):
    """オブジェクトごとのBIM情報"""

    element_type: EnumProperty(
        name="要素タイプ",
        items=ELEMENT_TYPES,
        default='NONE',
        description="建築要素の種類",
    )
    floor_level: EnumProperty(
        name="フロア",
        items=FLOOR_LEVELS,
        default='1F',
    )
    room_name: StringProperty(
        name="部屋名 / ゾーン",
        default="",
        description="この要素が属する部屋・ゾーン名",
    )
    construction_phase: EnumProperty(
        name="施工フェーズ",
        items=CONSTRUCTION_PHASES,
        default='DESIGN',
    )

    # ---- 材料 ----
    material_id: IntProperty(
        name="材料DB ID",
        default=0,
        description="データベース内の材料ID（0=未設定）",
    )
    material_name: StringProperty(
        name="材料名",
        default="未設定",
    )
    unit_cost: FloatProperty(
        name="単価 (円)",
        default=0.0,
        min=0,
        description="材料DBから取得、または手動入力",
    )
    quantity_unit: StringProperty(
        name="数量単位",
        default="m²",
    )

    # ---- 数量 ----
    auto_calc: BoolProperty(
        name="寸法から自動計算",
        default=True,
        description="オブジェクトの寸法から数量を自動算出",
    )
    quantity: FloatProperty(
        name="数量",
        default=0.0,
        min=0,
        description="手動入力する場合の数量",
    )

    # ---- メモ ----
    notes: StringProperty(
        name="備考",
        default="",
    )


# ------------------------------------------------------------------ #
#  ユーティリティ
# ------------------------------------------------------------------ #

def calc_quantity(obj, element_type):
    """オブジェクトの寸法から数量を算出（Blender単位=m）"""
    dims = obj.dimensions
    x, y, z = abs(dims.x), abs(dims.y), abs(dims.z)

    if element_type in ('WALL',):
        # 長さ × 高さ（主要面の面積）
        return max(x, y) * z
    elif element_type in ('FLOOR', 'ROOF'):
        # 平面積
        return x * y
    elif element_type in ('PILLAR', 'BEAM', 'FOUNDATION'):
        # 体積
        return x * y * z
    elif element_type in ('WINDOW', 'DOOR'):
        # 開口面積
        if x >= y:
            return x * z
        else:
            return y * z
    elif element_type == 'STAIR':
        # 投影面積
        return x * y
    else:
        # デフォルト：体積
        return x * y * z


def get_quantity_unit(element_type):
    """要素タイプから標準単位を返す"""
    unit_map = {
        'WALL':       'm²',
        'FLOOR':      'm²',
        'ROOF':       'm²',
        'PILLAR':     'm³',
        'BEAM':       'm³',
        'FOUNDATION': 'm³',
        'WINDOW':     '個',
        'DOOR':       '個',
        'STAIR':      'm²',
    }
    return unit_map.get(element_type, 'm²')


def auto_detect_type(obj_name):
    """オブジェクト名からBIM要素タイプを推定"""
    n = obj_name
    if any(k in n for k in ('壁', 'wall', 'Wall')):
        return 'WALL'
    if any(k in n for k in ('床', 'floor', 'Floor', 'スラブ')):
        return 'FLOOR'
    if any(k in n for k in ('柱', 'pillar', 'Pillar', 'column', 'Column')):
        return 'PILLAR'
    if any(k in n for k in ('梁', 'beam', 'Beam')):
        return 'BEAM'
    if any(k in n for k in ('屋根', 'roof', 'Roof')):
        return 'ROOF'
    if any(k in n for k in ('窓', 'window', 'Window')):
        return 'WINDOW'
    if any(k in n for k in ('ドア', 'door', 'Door', '扉')):
        return 'DOOR'
    if any(k in n for k in ('階段', 'stair', 'Stair')):
        return 'STAIR'
    if any(k in n for k in ('基礎', 'foundation', 'Foundation', '杭')):
        return 'FOUNDATION'
    return 'OTHER'


# ------------------------------------------------------------------ #
#  オペレーター
# ------------------------------------------------------------------ #

class BIM_OT_init_db(Operator):
    """データベースを初期化（デフォルト材料を追加）"""
    bl_idname = "bim.init_db"
    bl_label = "DBを初期化"

    def execute(self, context):
        try:
            db_init()
            path = get_db_path()
            self.report({'INFO'}, f"BIMデータベースを初期化: {path}")
        except Exception as e:
            self.report({'ERROR'}, f"DB初期化エラー: {e}")
        return {'FINISHED'}


# ---- 要素設定 ----

class BIM_OT_assign_element(Operator):
    """選択オブジェクトにBIM要素タイプを自動設定"""
    bl_idname = "bim.assign_element"
    bl_label = "BIM要素を自動設定"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        count = 0
        for obj in context.selected_objects:
            if obj.type != 'MESH':
                continue
            bim = obj.bim
            if bim.element_type == 'NONE':
                bim.element_type = auto_detect_type(obj.name)
            bim.quantity_unit = get_quantity_unit(bim.element_type)
            if bim.auto_calc:
                bim.quantity = calc_quantity(obj, bim.element_type)
            count += 1
        self.report({'INFO'}, f"{count}個のオブジェクトにBIM要素タイプを設定しました")
        return {'FINISHED'}


class BIM_OT_calc_quantity(Operator):
    """選択オブジェクトの数量を寸法から再計算"""
    bl_idname = "bim.calc_quantity"
    bl_label = "数量を再計算"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        count = 0
        for obj in context.selected_objects:
            if obj.type == 'MESH':
                bim = obj.bim
                bim.quantity = calc_quantity(obj, bim.element_type)
                count += 1
        self.report({'INFO'}, f"{count}個の数量を再計算しました")
        return {'FINISHED'}


class BIM_OT_clear_bim(Operator):
    """選択オブジェクトのBIM情報をリセット"""
    bl_idname = "bim.clear_bim"
    bl_label = "BIM情報をリセット"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        for obj in context.selected_objects:
            if obj.type == 'MESH':
                bim = obj.bim
                bim.element_type = 'NONE'
                bim.material_id = 0
                bim.material_name = "未設定"
                bim.unit_cost = 0.0
                bim.quantity = 0.0
                bim.notes = ""
        self.report({'INFO'}, "BIM情報をリセットしました")
        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)


# ---- 材料設定 ----

class BIM_OT_set_material(Operator):
    """DBの材料を選択オブジェクトに設定"""
    bl_idname = "bim.set_material"
    bl_label = "材料を設定"
    bl_options = {'REGISTER', 'UNDO'}

    material_id: IntProperty(name="材料ID", default=0)

    def execute(self, context):
        mat = db_get_material(self.material_id)
        if mat is None:
            self.report({'ERROR'}, "材料が見つかりません")
            return {'CANCELLED'}

        mat_id, name, category, unit, cost, desc = mat
        targets = [o for o in context.selected_objects if o.type == 'MESH']
        if not targets and context.active_object and context.active_object.type == 'MESH':
            targets = [context.active_object]

        for obj in targets:
            bim = obj.bim
            bim.material_id = mat_id
            bim.material_name = name
            bim.unit_cost = cost
            bim.quantity_unit = unit

        self.report({'INFO'}, f"材料「{name}」を{len(targets)}個のオブジェクトに設定")
        return {'FINISHED'}


class BIM_OT_open_material_picker(Operator):
    """材料選択ポップアップを表示"""
    bl_idname = "bim.open_material_picker"
    bl_label = "材料を選択"

    def execute(self, context):
        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=450)

    def draw(self, context):
        layout = self.layout
        if not db_exists():
            layout.label(text="DBが見つかりません。先にDBを初期化してください", icon='ERROR')
            layout.operator("bim.init_db")
            return
        try:
            mats = db_get_materials()
            if not mats:
                layout.label(text="材料が登録されていません")
                return
            prev_cat = None
            for mat in mats:
                mat_id, name, category, unit, cost, desc = mat
                if category != prev_cat:
                    layout.label(text=f"── {category} ──", icon='MATERIAL')
                    prev_cat = category
                op = layout.operator(
                    "bim.set_material",
                    text=f"{name}  ¥{cost:,.0f}/{unit}",
                    icon='DOT',
                )
                op.material_id = mat_id
        except Exception as e:
            layout.label(text=f"読み込みエラー: {e}", icon='ERROR')


# ---- 材料DB管理 ----

class BIM_OT_add_material(Operator):
    """材料データベースに新しい材料を追加"""
    bl_idname = "bim.add_material"
    bl_label = "材料を追加"
    bl_options = {'REGISTER', 'UNDO'}

    mat_name:     StringProperty(name="材料名",       default="新しい材料")
    category:     StringProperty(name="カテゴリ",     default="その他")
    unit:         EnumProperty(
        name="単位",
        items=[
            ('m²', 'm²', '平方メートル'),
            ('m³', 'm³', '立方メートル'),
            ('m',  'm',  'メートル'),
            ('個', '個', '個数'),
            ('式', '式', '一式'),
            ('kg', 'kg', 'キログラム'),
            ('本', '本', '本数'),
        ],
        default='m²',
    )
    unit_cost:    FloatProperty(name="単価 (円)",  default=0.0, min=0)
    description:  StringProperty(name="説明",         default="")

    def execute(self, context):
        if not db_exists():
            db_init()
        new_id = db_add_material(
            self.mat_name, self.category, self.unit,
            self.unit_cost, self.description
        )
        if new_id == -1:
            self.report({'ERROR'}, f"同名の材料が既に存在します: {self.mat_name}")
            return {'CANCELLED'}
        self.report({'INFO'}, f"材料「{self.mat_name}」を追加しました (ID:{new_id})")
        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=400)

    def draw(self, context):
        layout = self.layout
        col = layout.column(align=True)
        col.prop(self, "mat_name")
        col.prop(self, "category")
        col.prop(self, "unit")
        col.prop(self, "unit_cost")
        col.prop(self, "description")


class BIM_OT_edit_material(Operator):
    """材料を編集"""
    bl_idname = "bim.edit_material"
    bl_label = "材料を編集"
    bl_options = {'REGISTER', 'UNDO'}

    material_id:  IntProperty(name="材料ID",  default=0)
    mat_name:     StringProperty(name="材料名")
    category:     StringProperty(name="カテゴリ")
    unit:         EnumProperty(
        name="単位",
        items=[
            ('m²', 'm²', 'm²'), ('m³', 'm³', 'm³'), ('m', 'm', 'm'),
            ('個', '個', '個'), ('式', '式', '式'), ('kg', 'kg', 'kg'), ('本', '本', '本'),
        ],
        default='m²',
    )
    unit_cost:   FloatProperty(name="単価 (円)", default=0.0, min=0)
    description: StringProperty(name="説明")

    def execute(self, context):
        db_update_material(
            self.material_id, self.mat_name, self.category,
            self.unit, self.unit_cost, self.description
        )
        self.report({'INFO'}, f"材料「{self.mat_name}」を更新しました")
        return {'FINISHED'}

    def invoke(self, context, event):
        mat = db_get_material(self.material_id)
        if mat:
            _, name, cat, unit, cost, desc = mat
            self.mat_name = name
            self.category = cat
            self.unit = unit
            self.unit_cost = cost
            self.description = desc
        return context.window_manager.invoke_props_dialog(self, width=400)

    def draw(self, context):
        layout = self.layout
        col = layout.column(align=True)
        col.prop(self, "mat_name")
        col.prop(self, "category")
        col.prop(self, "unit")
        col.prop(self, "unit_cost")
        col.prop(self, "description")


class BIM_OT_delete_material(Operator):
    """材料をデータベースから削除"""
    bl_idname = "bim.delete_material"
    bl_label = "削除"
    bl_options = {'REGISTER', 'UNDO'}

    material_id: IntProperty(name="材料ID", default=0)

    def execute(self, context):
        db_delete_material(self.material_id)
        self.report({'INFO'}, "材料を削除しました")
        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)


# ---- レポート ----

class BIM_OT_show_summary(Operator):
    """BIM集計サマリーをポップアップ表示"""
    bl_idname = "bim.show_summary"
    bl_label = "BIM集計サマリー"

    _lines: list = []

    def execute(self, context):
        return {'FINISHED'}

    def invoke(self, context, event):
        self._build(context)
        return context.window_manager.invoke_props_dialog(self, width=520)

    def draw(self, context):
        layout = self.layout
        for line in self._lines:
            layout.label(text=line)

    def _build(self, context):
        type_labels = dict(ELEMENT_TYPES)
        type_data = defaultdict(lambda: {'count': 0, 'qty': 0.0, 'cost': 0.0, 'unit': ''})
        floor_cost = defaultdict(float)
        total_cost = 0.0
        bim_count = 0

        for obj in context.scene.objects:
            if obj.type != 'MESH':
                continue
            bim = obj.bim
            if bim.element_type == 'NONE':
                continue
            qty = calc_quantity(obj, bim.element_type) if bim.auto_calc else bim.quantity
            cost = qty * bim.unit_cost
            et = bim.element_type
            type_data[et]['count'] += 1
            type_data[et]['qty'] += qty
            type_data[et]['cost'] += cost
            type_data[et]['unit'] = bim.quantity_unit or get_quantity_unit(et)
            floor_cost[bim.floor_level] += cost
            total_cost += cost
            bim_count += 1

        lines = [
            "【 BIM 集計サマリー 】",
            f"  登録BIM要素数: {bim_count} 個",
            "─────────────────────────────────────────────",
            "  要素タイプ別:",
        ]
        for et, d in sorted(type_data.items()):
            label = type_labels.get(et, et)
            lines.append(
                f"    {label:6s}  {d['count']:3d}個  "
                f"{d['qty']:8.2f}{d['unit']}  ¥{d['cost']:>12,.0f}"
            )
        lines.append("─────────────────────────────────────────────")
        lines.append("  フロア別合計:")
        for fl in ('B3F','B2F','B1F','1F','2F','3F','4F','5F','RF'):
            if fl in floor_cost:
                lines.append(f"    {fl}:  ¥{floor_cost[fl]:>12,.0f}")
        lines.append("─────────────────────────────────────────────")
        lines.append(f"  合 計:  ¥{total_cost:>14,.0f}")
        self._lines = lines


class BIM_OT_generate_report(Operator):
    """BIMデータをCSVファイルに出力"""
    bl_idname = "bim.generate_report"
    bl_label = "CSVレポートを出力"

    filepath: StringProperty(subtype='FILE_PATH', default="bim_report.csv")
    filter_glob: StringProperty(default="*.csv", options={'HIDDEN'})

    def execute(self, context):
        try:
            count = self._write_csv(context)
            self.report({'INFO'}, f"CSVレポートを出力しました（{count}行）: {self.filepath}")
        except Exception as e:
            self.report({'ERROR'}, f"出力エラー: {e}")
            return {'CANCELLED'}
        return {'FINISHED'}

    def invoke(self, context, event):
        base = os.path.dirname(bpy.data.filepath) if bpy.data.filepath else os.path.expanduser("~")
        self.filepath = os.path.join(base, "bim_report.csv")
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def _write_csv(self, context):
        type_labels = dict(ELEMENT_TYPES)
        rows = []
        total_cost = 0.0

        for obj in sorted(context.scene.objects, key=lambda o: o.name):
            if obj.type != 'MESH':
                continue
            bim = obj.bim
            if bim.element_type == 'NONE':
                continue
            qty = calc_quantity(obj, bim.element_type) if bim.auto_calc else bim.quantity
            cost = qty * bim.unit_cost
            total_cost += cost

            dims = obj.dimensions
            rows.append({
                'オブジェクト名':  obj.name,
                '要素タイプ':      type_labels.get(bim.element_type, ''),
                'フロア':          bim.floor_level,
                '部屋名':          bim.room_name,
                '材料':            bim.material_name,
                '単位':            bim.quantity_unit or get_quantity_unit(bim.element_type),
                '数量':            f"{qty:.3f}",
                '単価(円)':        f"{bim.unit_cost:.0f}",
                '金額(円)':        f"{cost:.0f}",
                '寸法X(mm)':       f"{dims.x*1000:.1f}",
                '寸法Y(mm)':       f"{dims.y*1000:.1f}",
                '寸法Z(mm)':       f"{dims.z*1000:.1f}",
                '施工フェーズ':    bim.construction_phase,
                '備考':            bim.notes,
            })

        if not rows:
            raise ValueError("BIM要素が0件です。オブジェクトにBIM情報を設定してください。")

        fieldnames = [
            'オブジェクト名', '要素タイプ', 'フロア', '部屋名',
            '材料', '単位', '数量', '単価(円)', '金額(円)',
            '寸法X(mm)', '寸法Y(mm)', '寸法Z(mm)',
            '施工フェーズ', '備考',
        ]
        with open(self.filepath, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
            # 合計行
            empty = {k: '' for k in fieldnames}
            writer.writerow(empty)
            empty2 = {k: '' for k in fieldnames}
            empty2['オブジェクト名'] = '─── 合 計 ───'
            empty2['金額(円)'] = f"{total_cost:.0f}"
            writer.writerow(empty2)

        return len(rows)


# ------------------------------------------------------------------ #
#  UIパネル
# ------------------------------------------------------------------ #

class BIM_PT_object_props(Panel):
    """オブジェクトプロパティ内 BIM パネル"""
    bl_label = "BIM プロパティ"
    bl_idname = "BIM_PT_object_props"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "object"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        return context.active_object and context.active_object.type == 'MESH'

    def draw_header(self, context):
        obj = context.active_object
        bim = obj.bim
        self.layout.label(
            text="",
            icon='CHECKMARK' if bim.element_type != 'NONE' else 'ERROR',
        )

    def draw(self, context):
        layout = self.layout
        obj = context.active_object
        bim = obj.bim

        # 基本情報
        box = layout.box()
        box.label(text="基本情報", icon='OBJECT_DATA')
        col = box.column(align=True)
        col.prop(bim, "element_type")
        col.prop(bim, "floor_level")
        col.prop(bim, "room_name")
        col.prop(bim, "construction_phase")

        # 材料
        box2 = layout.box()
        box2.label(text="材料", icon='MATERIAL')
        row = box2.row(align=True)
        row.prop(bim, "material_name", text="")
        row.operator("bim.open_material_picker", text="選択", icon='EYEDROPPER')
        box2.prop(bim, "unit_cost")

        # 数量・金額
        box3 = layout.box()
        row_h = box3.row()
        row_h.label(text="数量 / 金額", icon='SNAP_INCREMENT')
        row_h.prop(bim, "auto_calc", text="自動計算")

        if bim.auto_calc:
            qty = calc_quantity(obj, bim.element_type)
            unit = get_quantity_unit(bim.element_type)
            box3.label(text=f"算出数量: {qty:.3f} {unit}")
        else:
            row_qty = box3.row(align=True)
            row_qty.prop(bim, "quantity")
            row_qty.prop(bim, "quantity_unit", text="")
            row_qty.operator("bim.calc_quantity", text="", icon='FILE_REFRESH')

        qty_disp = calc_quantity(obj, bim.element_type) if bim.auto_calc else bim.quantity
        total = qty_disp * bim.unit_cost
        box3.label(text=f"金額: ¥{total:,.0f}  (単価 ¥{bim.unit_cost:,.0f})")

        # 寸法表示
        dims = obj.dimensions
        box3.label(
            text=f"寸法: {dims.x*1000:.0f} × {dims.y*1000:.0f} × {dims.z*1000:.0f} mm"
        )

        # 備考
        layout.prop(bim, "notes")

        # アクション
        row_act = layout.row(align=True)
        row_act.operator("bim.assign_element", text="タイプ自動検出", icon='VIEWZOOM')
        row_act.operator("bim.clear_bim", text="リセット", icon='X')


class BIM_PT_sidebar(Panel):
    """Nパネル：BIM Manager メインパネル"""
    bl_label = "BIM Manager"
    bl_idname = "BIM_PT_sidebar"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "BIM"

    def draw(self, context):
        layout = self.layout

        # DB状態
        box = layout.box()
        row = box.row()
        row.label(text="データベース", icon='DISK_DRIVE')
        if db_exists():
            row.label(text="接続済", icon='CHECKMARK')
        else:
            row.label(text="未作成", icon='ERROR')
        box.label(text=get_db_path(), icon='FILE')
        box.operator("bim.init_db", text="DB を初期化 / 更新", icon='FILE_NEW')

        # 要素設定
        layout.separator()
        box2 = layout.box()
        box2.label(text="要素設定", icon='MESH_DATA')
        box2.operator("bim.assign_element",  text="選択要素にBIM自動設定", icon='PROPERTIES')
        box2.operator("bim.calc_quantity",   text="数量を再計算",          icon='FILE_REFRESH')
        box2.operator("bim.clear_bim",       text="BIM情報をリセット",     icon='X')

        # 選択オブジェクト情報
        obj = context.active_object
        if obj and obj.type == 'MESH':
            layout.separator()
            box3 = layout.box()
            bim = obj.bim
            box3.label(text=f"選択中: {obj.name}", icon='OBJECT_DATA')
            type_labels = dict(ELEMENT_TYPES)
            box3.label(text=f"タイプ: {type_labels.get(bim.element_type, '?')}")
            box3.label(text=f"フロア: {bim.floor_level}  |  材料: {bim.material_name}")
            qty = calc_quantity(obj, bim.element_type) if bim.auto_calc else bim.quantity
            box3.label(text=f"数量: {qty:.3f}  金額: ¥{qty * bim.unit_cost:,.0f}")

        # レポート
        layout.separator()
        box4 = layout.box()
        box4.label(text="レポート", icon='TEXT')
        box4.operator("bim.show_summary",    text="集計サマリー表示",  icon='INFO')
        box4.operator("bim.generate_report", text="CSV レポート出力",  icon='EXPORT')


class BIM_PT_materials_sidebar(Panel):
    """Nパネル：材料データベース管理"""
    bl_label = "材料データベース"
    bl_idname = "BIM_PT_materials_sidebar"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "BIM"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        layout.operator("bim.add_material", text="材料を追加", icon='ADD')

        if not db_exists():
            layout.label(text="DBが見つかりません", icon='ERROR')
            return

        try:
            mats = db_get_materials()
            if not mats:
                layout.label(text="材料が登録されていません（DBを初期化してください）")
                return

            prev_cat = None
            for mat in mats:
                mat_id, name, category, unit, cost, desc = mat
                if category != prev_cat:
                    layout.separator()
                    layout.label(text=f"── {category} ──", icon='MATERIAL')
                    prev_cat = category

                row = layout.row(align=True)
                set_op = row.operator(
                    "bim.set_material",
                    text=f"{name}  ¥{cost:,.0f}/{unit}",
                    icon='DOT',
                )
                set_op.material_id = mat_id

                edit_op = row.operator("bim.edit_material", text="", icon='GREASEPENCIL')
                edit_op.material_id = mat_id

                del_op = row.operator("bim.delete_material", text="", icon='TRASH')
                del_op.material_id = mat_id

        except Exception as e:
            layout.label(text=f"読み込みエラー: {e}", icon='ERROR')


# ------------------------------------------------------------------ #
#  アドオン設定
# ------------------------------------------------------------------ #

class BIM_Preferences(AddonPreferences):
    bl_idname = __name__

    db_path: StringProperty(
        name="DBパス",
        subtype='FILE_PATH',
        default="",
        description="SQLiteデータベースのパスを手動指定（空欄 = .blendファイルと同フォルダ）",
    )

    def draw(self, context):
        layout = self.layout
        layout.label(text="BIMデータベース設定", icon='DISK_DRIVE')
        layout.prop(self, "db_path")
        layout.label(text=f"現在のDBパス: {get_db_path()}", icon='FILE')
        layout.operator("bim.init_db", text="DBを初期化", icon='FILE_NEW')


# ------------------------------------------------------------------ #
#  登録
# ------------------------------------------------------------------ #

classes = [
    BIM_Preferences,
    BIM_ElementProps,
    BIM_OT_init_db,
    BIM_OT_assign_element,
    BIM_OT_calc_quantity,
    BIM_OT_clear_bim,
    BIM_OT_set_material,
    BIM_OT_open_material_picker,
    BIM_OT_add_material,
    BIM_OT_edit_material,
    BIM_OT_delete_material,
    BIM_OT_show_summary,
    BIM_OT_generate_report,
    BIM_PT_object_props,
    BIM_PT_sidebar,
    BIM_PT_materials_sidebar,
]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Object.bim = PointerProperty(type=BIM_ElementProps)
    # 初回起動時にDBを初期化（ファイルが存在しない場合のみ）
    try:
        if not db_exists():
            db_init()
    except Exception:
        pass


def unregister():
    del bpy.types.Object.bim
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
