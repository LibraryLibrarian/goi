# AGENTS.md

goiは、日本語入力（IME）の標準辞書で変換できない固有名詞等を登録して行く公開辞書プロジェクトです。このファイルは、goiで作業するAIエージェントと、PRをレビューするCodexに向けた説明です。人間向けの説明は[CONTRIBUTING.md](CONTRIBUTING.md)にあります。

## 構成

- `dictionary/`: 辞書データ（CC0 1.0、`dictionary/LICENSE`）。1つのJSONファイルが1つのグループで、複数の語を持ちます
- `src/dictctl/`: 辞書の検証・整形・ビルドを行うCLI（MIT）
- `schema/group.schema.json`: `src/dictctl/models.py`から生成したJSON Schema
- `spike/gboard-import/`: Gboardの取り込み挙動を実機で検証した記録。Gboardの形式の制約の根拠です

## コマンド

```bash
uv sync                    # 依存関係のインストール
uv run pytest              # テスト
uv run ruff check          # Lint
uv run ruff format         # 整形
uv run dictctl fmt         # 辞書ファイルの整形
uv run dictctl validate    # 辞書の検証
uv run dictctl build       # Gboard向けのZIPをdist/gboard/に出力
uv run dictctl schema      # models.pyを変更したときにスキーマを再生成
```

## 作業のルール

- テストやドキュメントの例には、実在の人物を使わないでください。CorsairやTriumphのようなブランド名を使います
- 不可視文字（ゼロ幅スペース、BOM、方向制御文字など）をソースに直接書かないでください。コードポイント（`chr(0xFEFF)`など）で書きます。`tests/test_source_hygiene.py`が検出します
- Gboardの取り込み形式（v2のヘッダー、LF、BOMなし、日本語の品詞名、表記は100文字かつ300バイト以内）は実機で確かめた制約です。変えるときは`spike/gboard-import/README.md`の結果と照らし合わせてください
- 同じ入力からは常に同じZIPが出力されるようにしてください（無圧縮・日時固定）
- 貢献者向けのドキュメントはです・ます調で書き、日本語と英数字の間に半角スペースを入れないでください

## Code Review Rules

指摘のタイトル・説明・修正案・要約は日本語で書いてください。コード・識別子・コマンド・引用は原文のままにしてください。

Ruff、pytest、`dictctl fmt --check`、`dictctl validate`など、CIで機械的に検出できることは指摘しないでください。

### 辞書データ（`dictionary/`）

- 追加・変更された語ごとに、`sources`のURLと`note`が、名前と読みを裏付けているかを確認してください。読みをどこで確認したかが書かれていない、読みが表記から機械的に読み下しただけに見える、といった場合は指摘してください
- 他の辞書やWebの一覧ページから機械的に抜き出したように見える追加（同じ一覧ページだけを出典にした大量の語など）は指摘してください
- 表記（`surface`）に、公式の表記と違う可能性（余計なスペース、全角・半角の違いなど）があれば指摘してください

### コード（`src/dictctl/`）

- Gboardの取り込み形式の制約や、同じ入力から同じZIPを出力する性質を壊す変更は指摘してください

### CIとリポジトリの設定（`.github/`、`AGENTS.md`）

- `pull_request_target`の使用、シークレットの使用、`permissions`での書き込み権限の追加、コミットSHAで固定していないActionの使用は指摘してください
- このファイル（`AGENTS.md`）を変更するPRは、その旨を指摘してください。メンテナーが内容を直接確認します
