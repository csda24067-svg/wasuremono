"""
忘れ物確認Webアプリ
実装済: 要件定義の機能No.1〜13すべて
拡張機能: 予定日入力・現在時刻表示・今日の予定の強調表示
          ※CSVに「予定日」列を追加(要件定義10章からの拡張)。旧3列CSVも読込可。
制約: Flask / CSV保存 / DBなし / ログインなし (要件定義 6章に準拠)
"""
import csv
import os
from datetime import datetime, date
from flask import Flask, render_template, request, redirect, url_for, flash

app = Flask(__name__)
app.secret_key = "pbl-wasuremono-dev-key"  # flash表示用(開発用)

# CSVデータ項目: 外出先, 持ち物, チェック状態, 予定日(拡張)
CSV_PATH = os.path.join(os.path.dirname(__file__), "data.csv")
HEADER = ["外出先", "持ち物", "チェック状態", "予定日"]
UNCHECKED = "未チェック"
CHECKED = "チェック済み"


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
                # 旧3列CSVには予定日が無いので空として扱う(後方互換)
                "予定日": (r.get("予定日") or "").strip(),
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


# ---------- 拡張: 予定日ヘルパー ----------
def parse_date(text):
    """YYYY-MM-DD形式の文字列をdateに変換。不正・空ならNone。"""
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def get_destination_date(destination):
    """外出先の予定日(date型)を返す。未設定ならNone。"""
    for r in load_rows():
        if r["外出先"] == destination and r["予定日"]:
            return parse_date(r["予定日"])
    return None


def set_destination_date(destination, date_str):
    """外出先の全行に予定日を書き込む(空文字なら削除)。"""
    rows = load_rows()
    for r in rows:
        if r["外出先"] == destination:
            r["予定日"] = date_str
    save_rows(rows)


def date_label(d, today):
    """予定日の表示ラベル(今日/あとN日/N日前)を返す。"""
    if d is None:
        return ""
    diff = (d - today).days
    if diff == 0:
        return "今日"
    if diff > 0:
        return f"あと{diff}日"
    return f"{-diff}日前"


# ---------- 画面: トップ(外出先一覧) ----------
@app.route("/")
def index():
    today = date.today()
    dest_info = []
    for d in get_destinations():
        item_rows = [r for r in get_items(d) if r["持ち物"]]
        done = sum(1 for r in item_rows if r["チェック状態"] == CHECKED)
        pdate = get_destination_date(d)
        dest_info.append({
            "name": d,
            "total": len(item_rows),
            "done": done,
            "ready": len(item_rows) > 0 and done == len(item_rows),
            "date": pdate.isoformat() if pdate else "",
            "date_label": date_label(pdate, today),
            "is_today": pdate == today,
            "_sort": (
                0 if pdate == today else                      # 今日が最優先
                1 if pdate and pdate > today else             # 次に未来(近い順)
                2 if pdate is None else 3,                    # 日付なし → 過去
                pdate or date.max,
            ),
        })
    dest_info.sort(key=lambda x: x["_sort"])

    weekdays = ["月", "火", "水", "木", "金", "土", "日"]
    now = datetime.now()
    now_text = f"{now.year}年{now.month}月{now.day}日({weekdays[now.weekday()]})"
    return render_template("index.html", destinations=dest_info, now_text=now_text)


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

    # 予定日(任意)の検証: 入力があるのに不正な形式ならエラー
    date_str = (request.form.get("date") or "").strip()
    if date_str and parse_date(date_str) is None:
        flash("予定日の形式が正しくありません", "error")
        return redirect(url_for("index"))

    # 外出先だけの行をプレースホルダとして持つのではなく、
    # 外出先の存在は「持ち物行」で表現する設計。
    # 持ち物ゼロでも外出先を保持するため、空持ち物の目印行を追加。
    rows = load_rows()
    rows.append({"外出先": name, "持ち物": "", "チェック状態": "", "予定日": date_str})
    save_rows(rows)
    flash(f"外出先「{name}」を登録しました", "success")
    return redirect(url_for("items", destination=name))


# ---------- 機能No.2,3,5: 持ち物登録 + 一覧表示 + 準備完了判定 ----------
@app.route("/items/<destination>")
def items(destination):
    if destination not in get_destinations():
        flash("指定された外出先は存在しません", "error")
        return redirect(url_for("index"))
    # 目印行(持ち物が空)は表示しない
    item_rows = [r for r in get_items(destination) if r["持ち物"]]

    # 準備完了判定 (No.5 / ユースケース図 include:全項目チェック済みか判定)
    # 持ち物が1件以上あり、かつ全てがチェック済みのとき準備完了
    all_done = len(item_rows) > 0 and all(
        r["チェック状態"] == CHECKED for r in item_rows
    )
    unchecked = [r for r in item_rows if r["チェック状態"] != CHECKED]

    today = date.today()
    pdate = get_destination_date(destination)

    return render_template(
        "items.html",
        destination=destination,
        items=item_rows,
        checked=CHECKED,
        all_done=all_done,
        unchecked_count=len(unchecked),
        unchecked_names=[r["持ち物"] for r in unchecked],  # No.11 未チェック強調用
        done_count=len(item_rows) - len(unchecked),        # No.13 進捗バー用
        total_count=len(item_rows),
        plan_date=pdate.isoformat() if pdate else "",      # 拡張: 予定日
        plan_label=date_label(pdate, today),
        is_today=(pdate == today),
    )


# ---------- 拡張: 予定日の設定・変更・削除 ----------
@app.route("/items/<destination>/set_date", methods=["POST"])
def set_date(destination):
    if destination not in get_destinations():
        flash("指定された外出先は存在しません", "error")
        return redirect(url_for("index"))

    date_str = (request.form.get("date") or "").strip()
    # 空 = 予定日を削除。入力ありなら形式を検証
    if date_str and parse_date(date_str) is None:
        flash("予定日の形式が正しくありません", "error")
        return redirect(url_for("items", destination=destination))

    set_destination_date(destination, date_str)
    if date_str:
        flash(f"予定日を {date_str} に設定しました", "success")
    else:
        flash("予定日を削除しました", "success")
    return redirect(url_for("items", destination=destination))


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
    # 新規持ち物は未チェックで保存。予定日は外出先の設定を引き継ぐ
    pdate = get_destination_date(destination)
    rows.append({
        "外出先": destination, "持ち物": item_name,
        "チェック状態": UNCHECKED,
        "予定日": pdate.isoformat() if pdate else "",
    })
    # この外出先の空目印行はもう不要なら除去
    rows = [r for r in rows if not (r["外出先"] == destination and r["持ち物"] == "")]
    save_rows(rows)
    flash(f"「{item_name}」を登録しました", "success")
    return redirect(url_for("items", destination=destination))


# ---------- 機能No.4: チェック切替 (Item.check / uncheck) ----------
@app.route("/items/<destination>/toggle", methods=["POST"])
def toggle_item(destination):
    item_name = (request.form.get("item") or "").strip()

    if destination not in get_destinations():
        flash("指定された外出先は存在しません", "error")
        return redirect(url_for("index"))

    rows = load_rows()
    found = False
    for r in rows:
        if r["外出先"] == destination and r["持ち物"] == item_name:
            # 状態遷移図: チェックを入れる / 外す の往復
            r["チェック状態"] = UNCHECKED if r["チェック状態"] == CHECKED else CHECKED
            found = True
            break

    if not found:
        flash("対象の持ち物が見つかりません", "error")
        return redirect(url_for("items", destination=destination))

    save_rows(rows)  # チェック状態をCSVに保存 (受け入れ基準5)
    return redirect(url_for("items", destination=destination))


# ---------- 機能No.8: 持ち物削除 ----------
@app.route("/items/<destination>/delete", methods=["POST"])
def delete_item(destination):
    item_name = (request.form.get("item") or "").strip()

    if destination not in get_destinations():
        flash("指定された外出先は存在しません", "error")
        return redirect(url_for("index"))

    rows = load_rows()
    new_rows = [r for r in rows
                if not (r["外出先"] == destination and r["持ち物"] == item_name)]

    if len(new_rows) == len(rows):
        flash("対象の持ち物が見つかりません", "error")
        return redirect(url_for("items", destination=destination))

    # 最後の持ち物を消しても外出先は残す(目印行を追加、予定日も引き継ぐ)
    if not any(r["外出先"] == destination for r in new_rows):
        pdate = next((r["予定日"] for r in rows if r["外出先"] == destination and r["予定日"]), "")
        new_rows.append({"外出先": destination, "持ち物": "", "チェック状態": "", "予定日": pdate})

    save_rows(new_rows)
    flash(f"「{item_name}」を削除しました", "success")
    return redirect(url_for("items", destination=destination))


# ---------- 機能No.9: 外出先削除 (持ち物ごと削除) ----------
@app.route("/destination/<destination>/delete", methods=["POST"])
def delete_destination(destination):
    if destination not in get_destinations():
        flash("指定された外出先は存在しません", "error")
        return redirect(url_for("index"))

    rows = [r for r in load_rows() if r["外出先"] != destination]
    save_rows(rows)
    flash(f"外出先「{destination}」を削除しました", "success")
    return redirect(url_for("index"))


# ---------- 機能No.10: チェック状態リセット (次回利用のため全て未チェックに) ----------
@app.route("/items/<destination>/reset", methods=["POST"])
def reset_checks(destination):
    if destination not in get_destinations():
        flash("指定された外出先は存在しません", "error")
        return redirect(url_for("index"))

    rows = load_rows()
    for r in rows:
        if r["外出先"] == destination and r["持ち物"]:
            r["チェック状態"] = UNCHECKED
    save_rows(rows)
    flash("チェック状態をリセットしました", "success")
    return redirect(url_for("items", destination=destination))


if __name__ == "__main__":
    app.run(debug=True)
