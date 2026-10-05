"""Dedicated web tabs, key|value schema, atomic replacement of A:B."""
import os
import json
from dataclasses import dataclass

@dataclass
class Row:
    key: str
    value: str = ""


class SheetClient:
    def __init__(self, spreadsheet_id, read_only=False):
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        raw = os.environ.get("GOOGLE_SA_JSON")
        if not raw:
            raise ValueError("GOOGLE_SA_JSON is required")
        info = json.loads(raw) if raw.lstrip().startswith("{") else json.loads(open(raw, encoding="utf-8").read())
        credentials = service_account.Credentials.from_service_account_info(
            info, scopes=["https://www.googleapis.com/auth/spreadsheets.readonly" if read_only
                    else "https://www.googleapis.com/auth/spreadsheets"])
        self.sid = spreadsheet_id
        self.api = build("sheets", "v4", credentials=credentials, cache_discovery=False).spreadsheets()

    def tabs(self):
        meta = self.api.get(spreadsheetId=self.sid, fields="sheets.properties").execute()
        return {s["properties"]["title"]: s["properties"] for s in meta.get("sheets", [])}

    def read_rows(self, tab):
        if tab not in self.tabs():
            return []
        escaped = tab.replace("'", "''")
        values = self.api.values().get(spreadsheetId=self.sid, range=f"'{escaped}'!A:B",
                                      valueRenderOption="UNFORMATTED_VALUE").execute().get("values", [])
        if not values or values[0] != ["key", "value"]:
            raise ValueError(f"{tab}: expected key|value header")
        rows = []
        for raw in values[1:]:
            key = raw[0] if raw else ""
            value = raw[1] if len(raw) > 1 else ""
            if not key and value:
                raise ValueError(f"{tab}: value without key")
            if not isinstance(key, str) or not isinstance(value, str):
                raise ValueError(f"{tab}: cells must be text")
            if key:
                rows.append(Row(key, value))
        return rows

    def replace_many(self, tables):
        tabs = self.tabs()
        requests = []
        next_id = max((p["sheetId"] for p in tabs.values()), default=0) + 1
        for tab, rows in tables.items():
            properties = tabs.get(tab)
            if properties is None:
                properties = {"sheetId": next_id}
                next_id += 1
                requests.append({"addSheet": {"properties": {
                    "sheetId": properties["sheetId"], "title": tab,
                    "gridProperties": {"rowCount": max(1000, len(rows)+1), "columnCount": 2}}}})
            elif properties["gridProperties"]["rowCount"] < len(rows)+1:
                requests.append({"appendDimension": {"sheetId": properties["sheetId"],
                    "dimension": "ROWS", "length": len(rows)+1-properties["gridProperties"]["rowCount"]}})
            values = [["key", "value"]] + [[r.key, r.value] for r in rows]
            requests.append({"updateCells": {
                "range": {"sheetId": properties["sheetId"], "startRowIndex": 0,
                          "startColumnIndex": 0, "endColumnIndex": 2},
                "rows": [{"values": [{"userEnteredValue": {"stringValue": v}} for v in row]} for row in values],
                "fields": "userEnteredValue"}})
        # One batch is atomic: also clears obsolete trailing cells, never clear+update.
        self.api.batchUpdate(spreadsheetId=self.sid, body={"requests": requests}).execute()
