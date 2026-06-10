# Spectral Render 使い方ガイド

Cycles を疑似スペクトルレンダラーとして動かす Blender アドオンの操作手順書です。
（対象: Blender 4.2 LTS 以降 / レンダラー: **Cycles**）

---

## 目次
1. [インストール](#1-インストール)
2. [基本の流れ（最短手順）](#2-基本の流れ最短手順)
3. [Spectral パネルの設定項目](#3-spectral-パネルの設定項目)
4. [マテリアル機能（分散・金属・ボリューム・上書き）](#4-マテリアル機能)
5. [結果画像の確認・保存](#5-結果画像の確認保存)
6. [アニメーションのレンダ](#6-アニメーションのレンダ)
7. [仕組み（なぜ Inject → Render → Restore なのか）](#7-仕組み)
8. [よくある質問・トラブルシュート](#8-よくある質問トラブルシュート)

---

## 1. インストール

### 方法A：Extension としてビルドして入れる（推奨）

1. ターミナル/PowerShell でリポジトリのルートに移動し、ビルドします。
   ```bash
   blender --command extension build --source-dir spectral_render
   ```
   → `spectral_render-0.1.0.zip` ができます。
2. Blender を起動し、`Edit > Preferences > Get Extensions` を開く。
3. 右上の `∨`（ドロップダウン）→ **Install from Disk…** → 先ほどの zip を選択。
4. 一覧に **Spectral Render** が出てチェックが入っていれば有効化完了。

### 方法B：フォルダを直接置く（開発時）

`spectral_render` フォルダごと、Blender のユーザー拡張フォルダにコピーします。

| OS | コピー先 |
|----|---------|
| Windows | `C:\Users\<ユーザー名>\AppData\Roaming\Blender Foundation\Blender\4.2\extensions\user_default\` |
| macOS | `~/Library/Application Support/Blender/4.2/extensions/user_default/` |
| Linux | `~/.config/blender/4.2/extensions/user_default/` |

コピー後、Blender を再起動し `Preferences > Get Extensions`（または Add-ons）で **Spectral Render** を有効化します。

### 確認
3D ビューポートで `N` キーを押し、右側のサイドバーに **「Spectral」タブ**が出れば成功です。

---

## 2. 基本の流れ（最短手順）

> グレー球などの簡単なシーンで、まず一連の流れを試すのがおすすめです。

1. **レンダラーを Cycles にする**
   `Properties > Render > Render Engine` を **Cycles** に。
2. **マテリアルの色を決める**
   オブジェクトに Principled BSDF マテリアルを付け、Base Color を設定。
   > ⚠️ 色は **Inject の前に**決めてください（係数は Inject 時に焼き込まれます）。
3. **対象オブジェクトを選択**
   スペクトル化したいオブジェクトを選択（パネルの Target を `All Materials` にすると全マテリアルが対象）。
4. **`N` → Spectral タブ**を開き、波長範囲・バンド数を確認（既定のままでOK）。
5. **`Inject Spectral Nodes`** を押す
   → マテリアルの Base Color が波長駆動のノードに置き換わります（元の状態は自動バックアップ）。
6. **`Spectral Render`** を押す
   → バンド数だけレンダが回り、合成結果が画像 **「Spectral Result」** に出力されます。
7. **結果を見る**（[第5章](#5-結果画像の確認保存)）。
8. 終わったら **`Restore`** を押す
   → ノードツリーが元通りに完全復元されます。

---

## 3. Spectral パネルの設定項目

`N` サイドバー → **Spectral** タブ（シーン全体の設定）。

| 項目 | 既定 | 説明 |
|------|------|------|
| **λ min / λ max (nm)** | 380 / 730 | レンダリングする波長範囲 |
| **Bands** | 16 | 波長バンド数 N。多いほど色が滑らかだが、**レンダ回数 = N** で遅くなる |
| **Samples / band** | 64 | 各バンドの Cycles サンプル数。合成で平均化されるので低めでも可 |
| **Illuminant** | D65 | 光源スペクトル。`D65`（昼光）/ `Equal Energy` / `Black Body`（色温度指定） |
| **Temperature (K)** | 6500 | Black Body 選択時のみ表示。色温度 |
| **Sampling** | Uniform | `Uniform`（等間隔）/ `Importance`（XYZ寄与で重要度サンプリング＝少バンドで同等品質） |
| **Uplift Textures** | ON | Base Color の画像テクスチャを**柄を保ったまま**テクセル単位でスペクトル化（下記4‑0）。OFF にすると定数色のみ |
| **Coeff Map Max Res** | 0 | 係数マップ解像度の上限（0＝元テクスチャと同じ）。4K 等で省メモリにしたいとき設定 |
| **Target** | Selected Objects | `Selected Objects`（選択物）/ `All Materials`（全マテリアル） |
| **Save Band EXRs** | OFF | 各バンドをシーンリニア EXR として保存（後段の再グレーディング用） |
| **EXR Folder** | `//spectral_bands/` | 上を ON にしたときの保存先 |

ボタン:
- **Inject Spectral Nodes** … 非破壊でノード注入
- **Restore** … 元に戻す
- **Spectral Render** … 静止画をスペクトル合成
- **Spectral Render Animation** … フレーム範囲を連番 EXR で出力

パネル下部に現在の **λ** と **Δλ** が表示されます（デバッグ用）。

---

## 4. マテリアル機能

`N` サイドバー → **Spectral** タブ内の **「Material Dispersion」** サブパネル
（アクティブオブジェクトのアクティブマテリアルに対して設定）。

設定後に **`Inject Spectral Nodes`** を押すと反映されます。優先順位は
**Spectrum Override > Spectral Metal > テクスチャ・アップリフト > 定数RGBアップリフト** です。

### 4-0. テクスチャ・アップリフト（木目・布などの柄を保持）
- Spectral パネルの **Uplift Textures** が ON のとき、Base Color に**画像テクスチャが直結**
  （または Mapping/UV 経由）しているマテリアルは、Inject 時に**テクセルごとに係数 (c0,c1,c2) を
  焼いた係数マップ画像**（`spectral_coeff_<マテリアル名>`）を自動生成し、元と同じ UV でサンプリング
  してスペクトル化します。**木目・布・タイルの柄を保ったまま**各バンドで反射率が出ます。
- 係数マップは Restore 時に自動削除されます（非破壊）。
- ColorRamp / Mix など**手続き型・複雑ノード**の Base Color は対象外で、従来どおり**定数色**に
  フォールバックします（必要なら一度テクスチャにベイクしてから使用）。
- 大きなテクスチャでメモリが気になる場合は **Coeff Map Max Res** で上限を設定（例 2048）。

### 4-1. Spectrum Override（任意の反射スペクトル）
- **Spectrum Override** を ON にし、**Spectrum CSV** に CSV ファイルを指定。
- CSV 形式（1行目はヘッダ）:
  ```csv
  wavelength,reflectance
  400,0.05
  500,0.6
  600,0.1
  700,0.05
  ```
- Base Color がこの実測スペクトルで駆動されます（特定オブジェクトに正確な色を与えたいとき）。

### 4-2. Dispersion（分散：プリズム・ガラス）
- ガラス/屈折を表すマテリアル（Glass BSDF、Refraction BSDF、または透過を持つ Principled）に対して、
  **Dispersion** を ON。
- **Mode**:
  - `IOR + Abbe` … `IOR (n_d)` と `Abbe (V_d)` を入力（カタログ値）。
  - `Cauchy A/B/C` … Cauchy 係数を直接入力。
- **Glass Preset**: ドロップダウンで `N-BK7` などを選び、右の **取り込みボタン（↧）** を押すと n_d / Abbe が自動入力されます。
- Inject すると IOR 入力が波長依存 `n(λ)` で駆動され、プリズムで虹色の分散が出ます。

### 4-3. Spectral Metal（金属：金・銅など）
- **Spectral Metal** を ON にし、**Metal** で `Gold / Silver / Copper / Aluminium` を選択。
- ⚠️ **対象の Principled BSDF の Metallic を 1.0 に**してください（パネルにも注意書きあり）。
- Inject すると Base Color が実測複素屈折率から計算した波長別 Fresnel 反射率で駆動され、
  金は赤を強く、青を弱く反射する…といった金属らしい色が出ます。

### 4-4. Spectral Volume（着色ガラス・媒質の吸収）
- Volume Absorption / Volume Scatter ノードを持つマテリアルで **Spectral Volume** を ON。
- **Transmission Tint** … 透過させたい色、**Density** … 濃さ。
- Inject すると体積の密度が波長依存吸収で駆動され、媒質越しの色が波長吸収で変化します。

---

## 5. 結果画像の確認・保存

スペクトル合成結果は、レンダービューではなく **「Spectral Result」という画像データ**に書き込まれます。

1. エディタを **Image Editor**（または UV Editing ワークスペース）に切り替える。
2. 上部の画像選択ドロップダウンから **「Spectral Result」** を選ぶ。
3. 表示されます。色は**シーンリニア**で保存されているため、
   シーンのビュー変換（`Properties > Render > Color Management` の AgX / Filmic / Standard）が
   表示時に自動適用されます（OCIO 整合）。

**保存**: Image Editor の `Image > Save As…` で任意の形式に保存できます
（EXR で保存すればリニアのまま、PNG なら表示変換込み）。

**バンド別 EXR**: パネルで `Save Band EXRs` を ON にしてレンダすると、
`band_000_383nm.exr` のように各波長帯が個別ファイルで保存され、Nuke/Natron 等で再グレーディングできます。

---

## 6. アニメーションのレンダ

1. シーンのフレーム範囲（`Output Properties > Frame Start / End`）を設定。
2. マテリアルに **Inject** を済ませておく。
3. パネルの **`Spectral Render Animation`** を押す。
   - 各フレームをスペクトル合成し、`//spectral_anim/spectral_0001.exr` … と連番のシーンリニア EXR で保存します。
   - `Save Band EXRs` が ON ならその保存先フォルダに出力されます。

> 注意: 注入された係数は固定です。**マテリアルの色をアニメーションさせる場合**は、その都度
> Restore → 色変更 → Inject が必要です（ジオメトリ・ライト・カメラのアニメはそのままで可）。

---

## 7. 仕組み

1. **アップリフト**: RGB 反射率を Jakob-Hanika 法で波長反射率 `S(λ)` に変換（3係数で表現）。
2. **バンドレンダ**: 波長範囲を N 分割し、各中心波長 `λ` で 1 回ずつモノクロレンダ。
   グローバル値 `spectral_lambda` をドライバ経由でマテリアルが参照します。
3. **合成**: 各バンドの結果に CIE 等色関数と光源 SPD を掛けて XYZ に蓄積 → 白色点で正規化 → sRGB 化。

**Inject → Render → Restore** という流れは、この「波長駆動ノード」を一時的に差し込み、
レンダ後に元へ戻すためです。注入時に元の接続/値を JSON でバックアップするので、
**Restore で必ず完全に元へ戻ります**（非破壊）。

---

## 8. よくある質問・トラブルシュート

| 症状 / 疑問 | 対処 |
|------|------|
| Spectral タブが出ない | アドオンが無効。`Preferences > Get Extensions/Add-ons` で Spectral Render を有効化。`N` でサイドバー表示 |
| 結果が出てこない | エディタを Image Editor にし、画像ドロップダウンで **Spectral Result** を選択 |
| 全体に色被りする | Illuminant 設定とシーンのライトが極端でないか確認。グレー球で R≈G≈B になるかをまず検証 |
| レンダが遅い | `Bands` を減らす／`Sampling` を **Importance** にする／`Samples / band` を下げる |
| 色を変えたのに反映されない | 係数は Inject 時に焼き込み。**Restore → 色変更 → Inject** をやり直す |
| 金属の色が出ない | Principled の **Metallic を 1.0** にし、Spectral Metal を ON にして Inject |
| 分散（虹）が出ない | ガラス/屈折ノードか、透過のある Principled が必要。Dispersion を ON にして Inject |
| Inject 後にノードがぐちゃぐちゃに見える | 一時ノードが差し込まれた状態です。**Restore** で必ず元に戻ります |
| Cycles 以外で使いたい | 本アドオンは Cycles 前提です。Render Engine を Cycles に |

---

困ったときは、`tests/integration_blender.py` を
`blender --background --python tests/integration_blender.py` で実行すると、
Inject→Render→Restore が正しく動くかを自動チェックできます。
