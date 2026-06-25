"""
忘れ物確認Webアプリ
今回実装: 外出先登録機能(No.1) + 持ち物登録機能(No.2) + 一覧表示(No.3) + CSV保存/読み込み(No.6,7)
制約: Flask / CSV保存 / DBなし / ログインなし (要件定義 6章に準拠)
"""
import csv
import os
from flask import Flask, render_template, request, redirect, url_for, flash

app = Flask(__name__)
app.secret_key = "pbl-wasuremono-dev-key"  # flash表示用(開発用)

# CSVデータ項目: 外出先, 持ち物, チェック状態 (要件定義 10章)
CSV_PATH = os.path.join(os.path.dirname(__file__), "data.csv")
HEADER = ["外出先", "持ち物", "チェック状態"]
UNCHECKED = "未チェック"


# ---------- CSVStorage 相当 (クラス図 CSVStorage: load/save) ----------
def load_rows():
    """CSVを読み込み、行のリスト(dict)を返す。ファイルが無ければ空リスト。"""
    if not os.path.exists(CSV_PATH):
        return []
    rows = []
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            # 外出先が無い行のみ無効(壊れたCSV対策)。持ち物空は「外出先のみ」の目印行として許容。
            dest = (r.get("外出先") or "").strip()
            if not dest:
                continue
            item = (r.get("持ち物") or "").strip()
            rows.append({
                "外出先": dest,
                "持ち物": item,
                # 持ち物空の目印行は状態も空。持ち物ありで状態欠損なら未チェック。
                "チェック状態": (r.get("チェック状態") or "").strip() or (UNCHECKED if item else ""),
            })
    return rows


def save_rows(rows):
    """行のリストをCSVに書き出す(全件上書き)。"""
    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=HEADER)
        writer.writeheader()
        writer.writerows(rows)


def get_destinations():
    """登録済み外出先を重複なし・登録順で返す。"""
    seen = []
    for r in load_rows():
        if r["外出先"] not in seen:
            seen.append(r["外出先"])
    return seen


def get_items(destination):
    """指定外出先の持ち物リストを返す。"""
    return [r for r in load_rows() if r["外出先"] == destination]


# ---------- 画面: トップ(外出先一覧) ----------
@app.route("/")
def index():
    return render_template("index.html", destinations=get_destinations())


# ---------- 機能No.1: 外出先登録 ----------
@app.route("/destination/add", methods=["POST"])
def add_destination():
    name = (request.form.get("destination") or "").strip()

    # 入力検証 (ユースケース図 extend: 外出先が未入力の場合)
    if not name:
        flash("外出先を入力してください", "error")
        return redirect(url_for("index"))
    if name in get_destinations():
        flash(f"外出先「{name}」は既に登録されています", "error")
        return redirect(url_for("index"))

    # 外出先だけの行をプレースホルダとして持つのではなく、
    # 外出先の存在は「持ち物行」で表現する設計。
    # 持ち物ゼロでも外出先を保持するため、空持ち物の目印行を追加。
    rows = load_rows()
    rows.append({"外出先": name, "持ち物": "", "チェック状態": ""})
    save_rows(rows)
    flash(f"外出先「{name}」を登録しました", "success")
    return redirect(url_for("items", destination=name))


# ---------- 機能No.2,3: 持ち物登録 + 一覧表示 ----------
@app.route("/items/<destination>")
def items(destination):
    if destination not in get_destinations():
        flash("指定された外出先は存在しません", "error")
        return redirect(url_for("index"))
    # 目印行(持ち物が空)は表示しない
    item_rows = [r for r in get_items(destination) if r["持ち物"]]
    return render_template("items.html", destination=destination, items=item_rows)


@app.route("/items/<destination>/add", methods=["POST"])
def add_item(destination):
    item_name = (request.form.get("item") or "").strip()

    if destination not in get_destinations():
        flash("指定された外出先は存在しません", "error")
        return redirect(url_for("index"))

    # 入力検証 (ユースケース図 extend: 持ち物が未入力の場合)
    if not item_name:
        flash("持ち物を入力してください", "error")
        return redirect(url_for("items", destination=destination))

    existing = [r["持ち物"] for r in get_items(destination) if r["持ち物"]]
    if item_name in existing:
        flash(f"「{item_name}」は既に登録されています", "error")
        return redirect(url_for("items", destination=destination))

    rows = load_rows()
    # 新規持ち物は未チェックで保存 (要件定義 10章)
    rows.append({"外出先": destination, "持ち物": item_name, "チェック状態": UNCHECKED})
    # この外出先の空目印行はもう不要なら除去
    rows = [r for r in rows if not (r["外出先"] == destination and r["持ち物"] == "")]
    save_rows(rows)
    flash(f"「{item_name}」を登録しました", "success")
    return redirect(url_for("items", destination=destination))


if __name__ == "__main__":
    app.run(debug=True)
