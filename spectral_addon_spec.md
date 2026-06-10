# Blender Spectral Render Addon — 開発スペック（Claude Code 用）

> このドキュメントは Claude Code（または同等のコーディングエージェント）が
> Blender 用スペクトルレンダリング・アドオンを段階的に実装するための仕様書です。
> 各フェーズは独立してビルド・テスト可能な単位になっています。
> 上から順に実装し、各フェーズ末尾の「完了条件」を満たしてから次へ進んでください。

---

## 0. プロジェクト概要

### 目的

Cycles を疑似的なスペクトルレンダラーとして動作させる Blender アドオンを作る。
RGB ベースのマテリアルを波長単位（spectral）に「アップリフト」し、波長バンドごとに
レンダリングして CIE XYZ で合成することで、分散・蛍光的色再現・金属の波長依存反射などの
物理的に正しい色をオフラインで得る。

### 基本原理（実装者が前提とする知識）

1. **スペクトルアップリフト**: RGB 反射率を波長反射率 `S(λ)` に変換する。
   Jakob-Hanika 法（2019）を用い、各色を 3 係数 `(c0, c1, c2)` で表現する。
2. **バンドレンダリング**: 波長範囲を `N` バンドに分割し、各バンド中心波長 `λ` で
   モノクロレンダリングを実行。グローバル値 `spectral_lambda` を各バンドにセットし、
   マテリアルのノードがその λ を参照して反射率・IOR などを計算する。
3. **合成**: 各バンドのレンダ結果に CIE 等色関数 `x̄(λ), ȳ(λ), z̄(λ)` を掛けて
   XYZ へ蓄積 → ディスプレイ変換（sRGB / OCIO）して最終画像を得る。

### 動作環境

| 項目 | 値 |
|------|-----|
| 対象 Blender | 4.2 LTS 以降（Extension 形式） |
| レンダラ | Cycles（GPU / OptiX 推奨） |
| 言語 | Python（Blender Python API, `bpy`） |
| 配布形式 | Blender Extension（`blender_manifest.toml`、extensions.blender.org 互換） |

---

## 1. リポジトリ構成（最終形）

```
spectral_render/
├── blender_manifest.toml      # 4.2+ Extension マニフェスト
├── __init__.py                # register/unregister のみ
├── properties.py              # Scene プロパティ（波長範囲・バンド数など）
├── ui/
│   └── panel.py               # N パネル（プロパティ表示）
├── core/
│   ├── jakob_hanika.py        # RGB → スペクトル係数の計算
│   ├── cmf.py                 # CIE 等色関数テーブル + λ→XYZ
│   ├── spd.py                 # 光源 SPD（Planck / D65 / 実測）
│   ├── dispersion.py          # Cauchy / Abbe → IOR(λ)
│   └── node_group.py          # 「Spectral Color」ノードグループ生成
├── ops/
│   ├── inject.py              # マテリアルへノード注入（非破壊）
│   ├── restore.py             # 元ノード接続の復元
│   └── render.py              # バンドループ・蓄積・合成
├── io/
│   └── exr.py                 # マルチレイヤー EXR 出力
└── data/
    ├── cie_1931_2deg.csv      # 等色関数
    ├── d65.csv                # D65 SPD
    └── metals/                # physicallybased.info の n,k データ
```

---

## Phase 1 — 最小アドオン（MVP）

最初に動く最小構成。固定等間隔バンドで、Base Color のみスペクトル化する。

### 1.1 パネル UI（`ui/panel.py` + `properties.py`）

`Scene` に以下のプロパティを定義し、3D ビューポートの N パネル
（カテゴリ "Spectral"）に表示する。

| プロパティ | 型 | 既定値 | 説明 |
|-----------|-----|--------|------|
| `lambda_min` | FloatProperty | 380.0 | 波長範囲の下限 (nm) |
| `lambda_max` | FloatProperty | 730.0 | 波長範囲の上限 (nm) |
| `band_count` | IntProperty | 16 | バンド数 N（min=3） |
| `samples_per_band` | IntProperty | 64 | バンドあたりサンプル数 |

パネルには上記プロパティと、`Inject Spectral Nodes` / `Restore` /
`Spectral Render` の 3 オペレータボタンを配置する。

### 1.2 Jakob-Hanika スペクトルアップリフト（`core/jakob_hanika.py`）

RGB（リニア sRGB, 0–1）から反射率スペクトル係数を求める。

反射率モデル:

```
S(λ) = sigmoid( c2 * λ̂² + c1 * λ̂ + c0 )
sigmoid(x) = 0.5 + x / (2 * sqrt(1 + x²))
```

ここで `λ̂` は波長を範囲内で正規化したスケール値（数値安定化のため、
360–830nm を [0,1] 等にマップ）。

実装方針（どちらか選択。MVP は B 推奨）:

- **A. 公式 LUT 移植**: Jakob-Hanika 論文の事前計算 3D LUT（RGB→係数）を
  バイナリ同梱し補間。高速だが容量大。
- **B. オンザフライ最適化**: Gauss-Newton 法で 3 係数をフィット。
  目的関数は「係数から復元したスペクトルを CIE 等色関数 + 光源 SPD で
  積分した XYZ → sRGB」と「入力 RGB」の差の最小化。
  1 色あたり数十回反復で収束。`scipy` は使えないので NumPy で自前実装する。

`def rgb_to_coeffs(rgb: tuple[float,float,float]) -> tuple[float,float,float]:`
を公開関数とする。

### 1.3 Spectral Color ノードグループ（`core/node_group.py`）

入力 RGB を受け、現在の `spectral_lambda` における反射率（スカラー）を出す
ノードグループ `SpectralColor` を生成する。

- グローバル λ の供給: Scene のカスタムプロパティ `spectral_lambda` を作り、
  Value ノードに **ドライバ** で接続（`scene["spectral_lambda"]` を参照）。
  レンダ時にこの値をバンドごとに書き換える。
- ノード内で `S(λ) = sigmoid(c2 λ̂² + c1 λ̂ + c0)` を Math ノード群で構築。
  係数 `c0,c1,c2` は `rgb_to_coeffs()` の結果を Value ノードに焼き込む。

### 1.4 ノード注入オペレータ（`ops/inject.py`）— 非破壊

> **実装上もっとも神経を使う部分。** 元の接続を必ず復元できる形で保存する。

手順:

1. 対象マテリアルを走査（選択オブジェクト or 全マテリアル、UI で切替）。
2. Principled BSDF の **Base Color** 入力に何が繋がっているか記録:
   - リンクあり → 接続元ソケットの identifier を保存
   - リンクなし → 既存の `default_value`（RGBA）を保存
3. 保存データは `material["_spectral_backup"]`（JSON 文字列）に格納し、
   セッション/ファイルをまたいでも復元可能にする。
4. `SpectralColor` ノードグループを挿入し、Base Color を置換接続する。
5. 既に注入済みのマテリアルはスキップ（冪等性を担保）。

### 1.5 復元オペレータ（`ops/restore.py`）

`material["_spectral_backup"]` を読み、`SpectralColor` ノードを削除して
元の接続/値を復元。バックアップキーも削除する。

### 1.6 Spectral Render オペレータ（`ops/render.py`）

```
XYZ_accum = zeros(H, W, 3)
for i in range(N):
    λ = lambda_min + (i + 0.5) * (lambda_max - lambda_min) / N
    scene["spectral_lambda"] = λ
    update drivers / depsgraph
    render → temp buffer (グレースケール強度)
    XYZ_accum += temp * CMF(λ) * Δλ        # CMF は (x̄,ȳ,z̄)
XYZ_accum *= 正規化係数（光源 SPD の Y 積分で割る）
RGB = XYZ_to_sRGB(XYZ_accum)              # 行列変換 + ガンマ
出力画像へ書き戻し
```

- バンドごとのレンダは `bpy.ops.render.render()` を使い、結果を
  `Render Result` から NumPy 配列へ取り出す。
- 進捗は `wm.progress_begin/update/end` で表示。

### Phase 1 完了条件

- [ ] N パネルが表示され、4 プロパティが編集できる
- [ ] Inject → Render → Restore が一連で動く
- [ ] グレーや原色のテストシーンで、RGB 通常レンダと
      スペクトル合成結果の色がおおむね一致する（露出・ホワイトバランス込み）
- [ ] Restore 後にノードツリーが完全に元へ戻る

---

## Phase 2 — 物理効果の拡充

MVP の枠組みに、波長依存の物理現象を載せる。

### 2.1 分散（`core/dispersion.py`）

マテリアルごとに屈折率の波長依存 `n(λ)` を与える。

- **Cauchy の式**: `n(λ) = A + B/λ² + C/λ⁴`（λ は µm）
- **Abbe 数 `V_d`** からの簡易導出にも対応（A, B を `n_d` と `V_d` から計算）。
- ガラス/屈折 BSDF の IOR 入力を、`spectral_lambda` ドライバ駆動の
  `IOR(λ)` ノードに接続する。
- UI: マテリアル単位で「IOR(n_d)」「Abbe 数」または「Cauchy A/B/C」を入力。

### 2.2 光源 SPD（`core/spd.py`）

各バンドで光源の強度を λ 駆動にする。

| プリセット | 計算 |
|-----------|------|
| 黒体（Planck） | `M(λ,T) = (2hc²/λ⁵) · 1/(exp(hc/(λkT)) − 1)`、UI で色温度 T 指定 |
| D65 | 同梱 CSV テーブルを補間 |
| 実測プリセット | CSV を `data/` に追加して読み込み |

光源の Strength / Color を λ ごとに書き換えるドライバ機構を用意する。
合成時の正規化（白がニュートラルになる）に SPD の Y 積分を用いる。

### 2.3 金属（複素 IOR）

physicallybased.info などの実測複素屈折率 `n(λ), k(λ)` を波長別に適用する。

- `data/metals/<material>.csv`（列: λ, n, k）を同梱・読み込み。
- 波長ごとの Fresnel 反射率を計算し、スペキュラ応答に反映。
  - Principled BSDF v2 の場合は適切な入力（IOR / Specular Tint 等）へ。
  - より正確には複素 Fresnel を Math ノードで構築するヘルパを用意。

### 2.4 ボリューム

波長依存の吸収・散乱係数 `σ_a(λ), σ_s(λ)`。
バンド独立レンダと相性が良い（各バンドで係数を切り替えるだけ）。

- Volume Absorption / Scatter の係数を `spectral_lambda` 駆動にする。
- UI: 吸収/散乱の波長プロファイル（CSV or 数式）を指定。

### Phase 2 完了条件

- [ ] プリズム的シーンで分散（虹色の縁）が出る
- [ ] 色温度を変えると画面全体の色がそれらしく変わる
- [ ] 金 / 銅 などが波長依存の色味で再現される
- [ ] 着色ガラス越しの色が波長吸収で変化する

---

## Phase 3 — 効率と品質

### 3.1 重要度サンプリング（ヒーロー波長的ストラティファイ）

固定等間隔バンドをやめ、波長を XYZ 寄与（特に輝度 ȳ）で重要度サンプリングする。

- 等色関数の輝度寄与に比例した確率密度で波長を選び、知覚的に効く波長へ
  重みを集中させる。不偏推定を保つため各サンプルを pdf で割る。
- 1 回のレンダで複数のストラティファイされた波長を扱う「ヒーロー波長」的手法へ。
- 目的: 同じノイズレベルをより少ないバンド数で達成する。

### 3.2 バンドあたりサンプル数の削減

合成時に多バンドが平均化されるため、バンドあたりサンプルは低めでよい。
`samples_per_band` を小さくしても最終ノイズが許容範囲に収まることを検証。

### 3.3 マルチレイヤー EXR 出力（`io/exr.py`）

各バンドを別レイヤーとしてマルチレイヤー EXR に書き出し、後段で再グレーディング
可能にする。レイヤー名は `band_<i>_<λ>nm` 形式。

### 3.4 OCIO 準拠の色変換

XYZ → ディスプレイ変換を Blender の OCIO コンフィグ経由で行い、
ビュー変換（AgX / Filmic / Standard）と整合させる。

### Phase 3 完了条件

- [ ] 重要度サンプリングで、同等品質をより少ないバンドで達成
- [ ] マルチレイヤー EXR が他ソフト（Nuke/Natron 等）で開ける
- [ ] OCIO ビュー変換と最終色が一致する

---

## Phase 4 — UX・配布

### 4.1 機能拡充

- **オブジェクト単位のスペクトル上書き**: 特定オブジェクトに任意の
  反射率スペクトル（CSV / 数式）を直接割り当て。
- **プリセット集**: 光源・金属・ガラスのプリセットライブラリ。
- **進捗 UI**: バンド進行状況・推定残り時間の表示。
- **アニメーション対応**: フレームごとのスペクトル係数キャッシュ（再計算回避）。

### 4.2 Extension パッケージ化

Blender 4.2+ の Extension 形式（extensions.blender.org 互換）でパッケージ。

`blender_manifest.toml` の最小例:

```toml
schema_version = "1.0.0"
id = "spectral_render"
version = "0.1.0"
name = "Spectral Render"
tagline = "Pseudo-spectral rendering for Cycles via band compositing"
maintainer = "Your Name <you@example.com>"
type = "add-on"
blender_version_min = "4.2.0"
license = ["SPDX:GPL-3.0-or-later"]

[permissions]
files = "Read bundled spectral data (CMF, SPD, metal IOR)"
```

- `__init__.py` は `register()` / `unregister()` のみ。
- `data/` の CSV はパッケージ同梱。読み込みは `__file__` 相対パスで解決。
- `blender --command extension build` でビルド可能なことを確認。

### Phase 4 完了条件

- [ ] オブジェクト単位上書きが効く
- [ ] アニメーションレンダがキャッシュ利用で高速化
- [ ] `extension build` が通り、クリーン環境でインストールできる

---

## 実装上の注意・既知のリスク

- **非破壊化が最重要**: ノード注入は必ず JSON バックアップ → 冪等注入 →
  完全復元のサイクルを守る。`material["_spectral_backup"]` をテストで往復検証。
- **ドライバ更新**: `spectral_lambda` 変更後は depsgraph 更新を明示的に行わないと
  レンダに反映されない場合がある。`scene.frame_set()` 相当の強制更新を入れる。
- **scipy 不可**: Blender 同梱 Python に scipy は無い。最適化・補間は NumPy で自作。
- **正規化**: 合成時の白色点（光源 SPD の Y 積分での割り戻し）を間違えると
  全体が色被りする。Phase 1 で必ず検証する。
- **GPU メモリ**: バンドループ中はシーンを保持したまま λ だけ変える。
  毎バンドでシーン再構築しないこと（OptiX 再コンパイルコスト回避）。

---

## 開発・テスト手順

1. `spectral_render/` を `scripts/addons/`（または Extension 用ディレクトリ）へ配置。
2. Blender を `--background` で起動し、最小シーン（グレー球 + エリアライト）で
   `Inject → Render → Restore` を回す自動テストスクリプトを `tests/` に用意。
3. RGB 通常レンダとスペクトル合成の差分（ΔE）を計測し回帰テストにする。
