#!/usr/bin/env python3
"""Build the architecture diagrams from their definitions in this file.

Why this exists
---------------
`.drawio` is the only source of truth for a diagram, and it is generated rather than
hand-edited so that a label change cannot land in one language and not the other. The
Japanese definition below is authoring; the English variant is produced by the LABELS
mapping, and a residue gate fails the build when a new Japanese label has no entry.

Icons come from the official AWS Architecture Icons asset package, which is not
committed: AWS permits using the assets in a diagram, not redistributing the library.
Pass the extracted package with --icons, and the SVG bytes end up base64-embedded in the
`.drawio` cells.

Traps this file exists to avoid, all of which produce a "successful" build with a
broken picture:

  1. `shape=image;image=data:image/svg+xml,<base64>` — comma, not `;base64,`. draw.io's
     parser expects the comma-only form, and the standard data URI form silently yields a
     blank icon. The MCP `insert_image_vertex` tool writes a form that renders in the
     editor and disappears on CLI export, which is why nothing here uses it.
  2. A double quote inside a `value="..."` attribute terminates it, and draw.io then
     drops that cell and every cell after it without an error. `xml_escape` below
     handles quotes for that reason; the stdlib `xml.sax.saxutils.escape` does not, and
     importing it also trips bandit's B406 for a function that parses nothing.
  3. An icon label sits *below* its 80px box and overflows sideways as far as the text
     needs, so "Amazon FSx for\nNetApp ONTAP" crosses the group boundary it belongs to.
     `whiteSpace=wrap` looks like the fix and is not: draw.io then wraps to the 80px box
     and breaks mid-word, producing "Amazon Quick" / "Sight" and "振動セン" / "サー".
     The official guidance is at most two lines and never a break inside a word, so the
     breaks are written into the label as `\n` and the layout gives each column the room
     a two-line name needs.
  4. An edge left to route itself takes the shortest orthogonal path, which is regularly
     straight through an icon or through the label under it. Because the label occupies
     the space directly below a box, an edge must never leave a box downwards. Hence the
     explicit exit/entry/waypoint arguments: routing is stated, not inferred.

Usage:
    python scripts/build_diagrams.py --icons /tmp/aws-icons [--export]

--export additionally renders SVG and PNG through the draw.io CLI, which is where a
layout problem actually becomes visible. XML validity proves nothing about the picture.

Exit codes: 0 built, 1 a definition, a mapping or an export failed.
"""

from __future__ import annotations

import argparse
import base64
import re
import subprocess  # nosec B404  # fixed argv, never a shell string
import sys
import tempfile
import xml.etree.ElementTree as ET  # nosec B405  # noqa: S405  parsing our own output
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DIAGRAM_DIR = REPO_ROOT / "docs" / "diagrams"
IMAGE_DIR = REPO_ROOT / "docs" / "images"
PNG_DIR = IMAGE_DIR / "png"
DRAWIO_BIN = Path("/Applications/draw.io.app/Contents/MacOS/draw.io")

SERVICE = 80  # official service icon canvas; never rescaled
RESOURCE = 48  # official resource icon canvas

# Only our own strokes, text and fills change between themes. The AWS icons never do:
# recolouring one is not permitted, and they read on either background as shipped.
#
# The dark variant is a real palette rather than the draw.io CLI's `--theme dark`. That
# flag produces a genuinely dark PNG, but for SVG it only adds `color-scheme: dark` and a
# transparent background while leaving every explicit colour alone — measured: the
# stroke/fill census of a `--theme dark` SVG is identical to the light one. Rendered on a
# light page it is the light diagram. Exporting both formats from a dark-palette source
# also keeps the PNG and the SVG showing the same thing.
THEMES = {
    "light": {
        "ink": "#232F3E",
        "canvas": "#FFFFFF",
        "note_fill": "#F7F7F7",
        "note_stroke": "#AAB7B8",
        "box_fill": "#FFFFFF",
    },
    # Contrast against the canvas: 12.6:1 for text, well past WCAG AA for body text.
    "dark": {
        "ink": "#D5DBDB",
        "canvas": "#16191F",
        "note_fill": "#232F3E",
        "note_stroke": "#5F6B7A",
        "box_fill": "#232F3E",
    },
}


def edge_style(p: dict[str, str]) -> str:
    return (
        "edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;"
        f"endArrow=open;endFill=0;strokeColor={p['ink']};strokeWidth=1;"
        f"fontSize=11;fontColor={p['ink']};labelBackgroundColor={p['canvas']};"
    )


def group_style(p: dict[str, str]) -> str:
    return (
        "rounded=0;html=1;dashed=1;dashPattern=8 4;fillColor=none;"
        f"strokeColor={p['ink']};verticalAlign=top;align=left;spacingLeft=8;spacingTop=4;"
        f"fontSize=12;fontColor={p['ink']};fontStyle=1;"
    )


def note_style(p: dict[str, str]) -> str:
    return (
        f"rounded=0;html=1;whiteSpace=wrap;fillColor={p['note_fill']};"
        f"strokeColor={p['note_stroke']};align=left;verticalAlign=top;spacing=8;"
        f"fontSize=11;fontColor={p['ink']};"
    )


def plain_style(p: dict[str, str]) -> str:
    return (
        f"rounded=1;html=1;whiteSpace=wrap;fillColor={p['box_fill']};"
        f"strokeColor={p['ink']};fontSize=11;fontColor={p['ink']};"
    )

# Icon paths relative to the extracted asset package. The filename is the authority on
# the service name: if a name cannot be found here, the name is wrong.
ICONS = {
    "fsxn": "Architecture-Service-Icons_07312026/Arch_Storage/64/Arch_Amazon-FSx-for-NetApp-ONTAP_64.svg",
    "bedrock": "Architecture-Service-Icons_07312026/Arch_Artificial-Intelligence/64/Arch_Amazon-Bedrock_64.svg",
    "agentcore": "Architecture-Service-Icons_07312026/Arch_Artificial-Intelligence/64/Arch_Amazon-Bedrock-AgentCore_64.svg",
    "athena": "Architecture-Service-Icons_07312026/Arch_Analytics/64/Arch_Amazon-Athena_64.svg",
    "glue": "Architecture-Service-Icons_07312026/Arch_Analytics/64/Arch_AWS-Glue_64.svg",
    "sagemaker": "Architecture-Service-Icons_07312026/Arch_Artificial-Intelligence/64/Arch_Amazon-SageMaker-AI_64.svg",
    "iotcore": "Architecture-Service-Icons_07312026/Arch_Internet-of-Things/64/Arch_AWS-IoT-Core_64.svg",
    "lambda": "Architecture-Service-Icons_07312026/Arch_Compute/64/Arch_AWS-Lambda_64.svg",
    "s3": "Architecture-Service-Icons_07312026/Arch_Storage/64/Arch_Amazon-Simple-Storage-Service_64.svg",
    "kinesis": "Architecture-Service-Icons_07312026/Arch_Analytics/64/Arch_Amazon-Kinesis-Data-Streams_64.svg",
    "firehose": "Architecture-Service-Icons_07312026/Arch_Analytics/64/Arch_Amazon-Data-Firehose_64.svg",
    "sns": "Architecture-Service-Icons_07312026/Arch_Application-Integration/64/Arch_Amazon-Simple-Notification-Service_64.svg",
    "opensearch": "Architecture-Service-Icons_07312026/Arch_Analytics/64/Arch_Amazon-OpenSearch-Service_64.svg",
    "quick": "Architecture-Service-Icons_07312026/Arch_Business-Applications/64/Arch_Amazon-Quick_64.svg",
    "s3ap": "Resource-Icons_07312026/Res_Storage/Res_Amazon-Simple-Storage-Service_General-Access-Points_48.svg",
    "camera": "Resource-Icons_07312026/Res_IoT/Res_AWS-IoT_Thing_Camera_48.svg",
    "vibration": "Resource-Icons_07312026/Res_IoT/Res_AWS-IoT_Thing_Vibration-Sensor_48.svg",
}

# Reference markers are global, not per figure. Two figures sit next to each other in the
# README, so a number that means one thing in one and something else in the other is read as
# the same note. That happened once already: the overview and pattern 05 both grew a ※5.
#
#   ※1 access point prerequisites      ※6 permission asymmetry
#   ※2 two-layer authorization         ※7 a standard S3 bucket is required here
#   ※3 event notifications unavailable ※8 no official walkthrough via an access point
#   ※4 hardware testing incomplete     ※9 optional path, not created by default
#   ※5 not implemented in this repository
#
# Japanese label -> English label. A Japanese label with no entry fails the build.
LABELS = {
    "AWS クラウド": "AWS Cloud",
    "オンプレミス": "On-premises",
    "既存のファイル共有": "Existing file share",
    "カメラ": "Camera",
    "振動センサー": "Vibration sensor",
    "ローカルストレージ": "Local storage",
    "Kafka / ClickHouse": "Kafka / ClickHouse",
    "ダッシュボード": "Dashboards",
    "文書": "Documents",
    "ベクトルストア": "Vector store",
    "利用者": "Users",
    "NFS / SMB": "NFS / SMB",
    "NFS 書き込み": "NFS write",
    "イベント": "Events",
    "同期": "Sync",
    "同期 / 読み取り配信": "Sync / read delivery",
    # Markers tie a note to the thing it qualifies. A note with nothing to point at is
    # read as a general disclaimer, which is not what these say.
    "エッジ拠点 ※4": "Edge site *4",
    "セルラー接続（任意）※9": "Cellular connectivity (optional) *9",
    "SORACOM プラットフォーム": "SORACOM platform",
    "Amazon Bedrock\nKnowledge Bases": "Amazon Bedrock\nKnowledge Bases",
    "Amazon Kinesis\nData Streams": "Amazon Kinesis\nData Streams",
    "Amazon Data\nFirehose": "Amazon Data\nFirehose",
    "Amazon Simple\nStorage Service ※7": "Amazon Simple\nStorage Service *7",
    "Amazon\nSageMaker AI ※8": "Amazon\nSageMaker AI *8",
    "MQTT": "MQTT",
    "PutObject": "PutObject",
    "テレメトリ": "Telemetry",
    "AWS クラウド ※5": "AWS Cloud *5",
    "S3 Access Point\n※1 ※2": "S3 Access Point\n*1 *2",
    "S3 Access Point\n※3": "S3 Access Point\n*3",
    "取り込み ※6": "Ingestion *6",
    "スクリーニング": "Screening",
    "詳細判定": "Detailed verdict",
    "通知": "Notification",
    "判定結果": "Verdicts",
    "検索": "Retrieval",
    "問い合わせ": "Query",
    "補足": "Notes",
    "※1 S3 Access Point は ONTAP 9.17.1 以降が必要": "*1 S3 access points require ONTAP 9.17.1 or later",
    "同一リージョン・同一アカウント・マウント済みボリュームであること": "Same Region, same account, and a mounted volume",
    "※2 認可は 2 層で評価される": "*2 Authorization is evaluated in two layers",
    "IAM とファイルシステム権限の両方を通る必要がある": "A request has to pass both IAM and file system permissions",
    "※3 イベント通知は使えない": "*3 Event notifications are unavailable",
    "ファイル到着の起点は FPolicy / 明示的な呼び出し / ポーリング": "File arrival is triggered by FPolicy, an explicit call, or polling",
    "※4 実機テスト未完了": "*4 Hardware testing incomplete",
    "エッジ側と ONTAP 連携は未検証": "The edge side and ONTAP integration are unverified",
    "※7 ここは標準の S3 バケットが必要": "*7 A standard S3 bucket is required here",
    "Athena のクエリ結果の出力先は S3 バケットであることが公式に必須。Amazon Data Firehose の配信先も S3 バケット ARN で、access point を受けるかは未検証":
        "Athena's query results location is officially required to be an S3 bucket. Firehose also takes an S3 bucket ARN as its destination, and whether it accepts an access point is unverified",
    "Athena のクエリ結果の出力先は S3 バケットであることが公式に必須。判定結果も現在は共有スタックのバケットに書いている":
        "Athena's query results location is officially required to be an S3 bucket. Verdicts are currently written to the shared stack's bucket as well",
    "※8 S3 Access Point 経由の利用に公式手順がない": "*8 No official walkthrough for use via an access point",
    "※9 この経路は任意で、既定では作られない": "*9 This path is optional and is not created by default",
    "SoracomOperatorId を指定したときだけ IAM ロールが作られる。SORACOM 側のアカウントが ExternalId 付きでそのロールを引き受け、Kinesis と S3 の raw/ 配下に書く":
        "The IAM role is created only when SoracomOperatorId is supplied. SORACOM's own account assumes it with that value as the ExternalId and writes to Kinesis and to raw/ in the bucket",
    "公式手順があるのは Athena / AWS Lambda / AWS Glue / Bedrock Knowledge Bases / EMR Serverless / CloudFront / Transfer Family":
        "Official walkthroughs exist for Athena, AWS Lambda, AWS Glue, Bedrock Knowledge Bases, EMR Serverless, CloudFront, and Transfer Family",
    "※5 このリポジトリに実装なし": "*5 No implementation in this repository",
    "AWS が公式手順を公開している": "AWS publishes an official walkthrough",
    "※6 権限の非対称に注意": "*6 Mind the permission asymmetry",
    "単一の資格情報で全文書を取り込むと利用者ごとの区別が失われる": "Ingesting every document under one identity loses the per-user distinction",
}

# U+203B (※) sits outside every CJK block, so a reference marker would otherwise survive
# untranslated into the English file with the residue gate reporting nothing. U+3000-303F
# covers 、。「」 for the same reason.
CJK = re.compile(r"[\u203b\u3000-\u303f\u3040-\u30ff\u4e00-\u9fff\uff00-\uffef]")


def xml_escape(text: str, newlines: bool = False) -> str:
    """Escape for use inside a double-quoted XML attribute value.

    Ampersand first: escaping it after `<` would turn `&lt;` into `&amp;lt;`.
    """
    escaped = (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
    return escaped.replace("\n", "&#10;") if newlines else escaped


def label_html(text: str) -> str:
    """Escape a label, turning an explicit `\\n` into a line break draw.io honours.

    `&#10;` is not a break in an HTML label; `<br>` is, and it has to reach the file
    escaped because an attribute value cannot hold a raw `<`.
    """
    return "&lt;br&gt;".join(xml_escape(part) for part in text.split("\n"))


class Diagram:
    """Accumulates cells and writes a `.drawio` whose XML is verified after writing."""

    def __init__(self, name: str, title: str, width: int, height: int,
                 theme: str = "light") -> None:
        self.name = name
        self.title = title
        self.width = width
        self.height = height
        self.theme = theme
        self.p = THEMES[theme]
        self.cells: list[str] = []
        self.labels: list[str] = []

    def _value(self, text: str) -> str:
        return xml_escape(text, newlines=True)

    def group(self, cid: str, label: str, x: int, y: int, w: int, h: int) -> None:
        self.labels.append(label)
        self.cells.append(
            f'<mxCell id="{cid}" value="{label_html(label)}" style="{group_style(self.p)}" '
            f'vertex="1" parent="1"><mxGeometry x="{x}" y="{y}" width="{w}" '
            f'height="{h}" as="geometry"/></mxCell>'
        )

    def icon(self, cid: str, icon_key: str, label: str, x: int, y: int, uri: str,
             size: int = SERVICE) -> None:
        self.labels.append(label)
        style = (
            "sketch=0;html=1;shape=image;verticalLabelPosition=bottom;verticalAlign=top;"
            f"labelPosition=center;align=center;imageAspect=1;aspect=fixed;fontSize=11;"
            f"fontColor={self.p['ink']};image={uri};"
        )
        self.cells.append(
            f'<mxCell id="{cid}" value="{label_html(label)}" style="{style}" '
            f'vertex="1" parent="1"><mxGeometry x="{x}" y="{y}" width="{size}" '
            f'height="{size}" as="geometry"/></mxCell>'
        )

    def box(self, cid: str, label: str, x: int, y: int, w: int, h: int) -> None:
        self.labels.append(label)
        self.cells.append(
            f'<mxCell id="{cid}" value="{label_html(label)}" style="{plain_style(self.p)}" '
            f'vertex="1" parent="1"><mxGeometry x="{x}" y="{y}" width="{w}" '
            f'height="{h}" as="geometry"/></mxCell>'
        )

    def note(self, cid: str, lines: list[str], x: int, y: int, w: int, h: int) -> None:
        for line in lines:
            self.labels.append(line)
        # Bold headline, detail on the next line, per the figure-annotation convention.
        #
        # The markup is escaped in full. An attribute value cannot contain a raw `<`,
        # so draw.io stores label HTML escaped and unescapes it on read; writing raw
        # tags here produces a file that fails to parse. The gate in write() caught
        # exactly that on the first run.
        parts = [f"<b>{lines[0]}</b>"]
        for index, line in enumerate(lines[1:]):
            parts.append(f"<b>{line}</b>" if index % 2 == 0 else line)
        html = self._value("<br>".join(parts))
        self.cells.append(
            f'<mxCell id="{cid}" value="{html}" style="{note_style(self.p)}" vertex="1" '
            f'parent="1"><mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" '
            f'as="geometry"/></mxCell>'
        )

    def edge(self, cid: str, source: str, target: str, label: str = "",
             offset: tuple[float, int, int] | None = None,
             exit: tuple[float, float] | None = None,
             entry: tuple[float, float] | None = None,
             points: list[tuple[int, int]] | None = None,
             both: bool = False) -> None:
        """Connect two cells along a stated route.

        exit/entry are fractions of the source/target box, so (1, 0.5) is the middle of
        the right edge. Leave them off only when the two boxes are already aligned and
        the automatic route is a single straight segment. `points` are the corners the
        line must turn at; `both` draws an arrowhead at each end, which is how a
        bidirectional relationship stays one line instead of two overlapping ones.

        offset is (along, dx, dy). `along` runs from -1 at the source to +1 at the
        target, so the midpoint is 0 — not 0.5. Passing 0.5 puts the label three
        quarters of the way along, which is how a label ends up on top of the icon it
        was meant to sit beside.
        """
        if label:
            self.labels.append(label)
        style = edge_style(self.p)
        if exit is not None:
            style += f"exitX={exit[0]};exitY={exit[1]};exitDx=0;exitDy=0;"
        if entry is not None:
            style += f"entryX={entry[0]};entryY={entry[1]};entryDx=0;entryDy=0;"
        if both:
            style += "startArrow=open;startFill=0;"

        inner = ""
        if offset is not None:
            inner += f'<mxPoint as="offset" x="{offset[1]}" y="{offset[2]}"/>'
        if points:
            corners = "".join(f'<mxPoint x="{x}" y="{y}"/>' for x, y in points)
            inner += f'<Array as="points">{corners}</Array>'
        along = f' x="{offset[0]}"' if offset is not None else ""
        geometry = (
            f'<mxGeometry{along} relative="1" as="geometry">{inner}</mxGeometry>'
            if inner else '<mxGeometry relative="1" as="geometry"/>'
        )
        self.cells.append(
            f'<mxCell id="{cid}" value="{self._value(label)}" style="{style}" '
            f'edge="1" parent="1" source="{source}" target="{target}">{geometry}</mxCell>'
        )

    def to_xml(self) -> str:
        body = "".join(self.cells)
        return (
            '<mxfile host="build_diagrams.py">'
            f'<diagram name="{self._value(self.title)}">'
            f'<mxGraphModel dx="{self.width}" dy="{self.height}" grid="0" '
            'gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" '
            f'page="1" pageScale="1" pageWidth="{self.width}" '
            f'pageHeight="{self.height}" math="0" shadow="0" '
            # Without this the export is transparent, and a dark figure with light text
            # is invisible on the light page it gets embedded in.
            f'background="{self.p["canvas"]}">'
            '<root><mxCell id="0"/><mxCell id="1" parent="0"/>'
            f"{body}</root></mxGraphModel></diagram></mxfile>"
        )

    def write(self, path: Path) -> None:
        xml = self.to_xml()
        path.parent.mkdir(parents=True, exist_ok=True)
        # Trailing newline: end-of-file-fixer rewrites the file without one, and a
        # generated artifact that a hook wants to edit is a build that is never clean.
        path.write_text(xml + "\n", encoding="utf-8")
        # A gate, not a formality: a dropped cell is invisible without it.
        ET.parse(path)  # nosec B314  # noqa: S314  our own generated file
        for cell in re.findall(r'id="([^"]+)"', xml):
            if f'id="{cell}"' not in path.read_text(encoding="utf-8"):
                raise SystemExit(f"{path}: cell {cell} did not land in the file")


def data_uri(icons_root: Path, key: str) -> str:
    path = icons_root / ICONS[key]
    if not path.is_file():
        raise SystemExit(f"icon not found: {path}")
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    # Comma, not ";base64,". The standard data URI form renders blank in draw.io.
    return f"data:image/svg+xml,{b64}"


def translate(diagram: Diagram) -> Diagram:
    """Produce the English variant, failing when a label has no mapping."""
    xml = diagram.to_xml()
    missing = sorted({label for label in diagram.labels if CJK.search(label) and label not in LABELS})
    if missing:
        for label in missing:
            print(f"  no LABELS entry for: {label!r}", file=sys.stderr)
        raise SystemExit(f"{diagram.name}: {len(missing)} label(s) have no translation")

    english = Diagram(diagram.name + "-en", diagram.title, diagram.width,
                      diagram.height, diagram.theme)
    # Longest first: "エッジ拠点 ※4" has to be replaced before "エッジ拠点" would
    # consume its prefix and leave the marker behind.
    for ja, en in sorted(LABELS.items(), key=lambda kv: -len(kv[0])):
        xml = xml.replace(label_html(ja), label_html(en))
    english.cells = [xml]  # already a full document; write() handles it below
    english._prebuilt = xml  # type: ignore[attr-defined]
    return english


def write_english(xml: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(xml + "\n", encoding="utf-8")
    ET.parse(path)  # nosec B314  # noqa: S314  our own generated file
    residue = CJK.findall(path.read_text(encoding="utf-8"))
    if residue:
        raise SystemExit(
            f"{path}: {len(residue)} CJK character(s) remain after translation: "
            f"{''.join(sorted(set(residue))[:20])}"
        )


# --------------------------------------------------------------------------------------
# Diagram definitions
# --------------------------------------------------------------------------------------


def overview(uri, theme: str) -> Diagram:
    """Whole-repository scope: two ingestion paths, one storage spine, three consumers.

    Rows are 220px apart because an icon is 80px and its wrapped label takes up to
    LABEL_H below it; anything tighter and a label meets the row beneath it.
    """
    d = Diagram("architecture-overview", "Architecture overview", 1300, 1330, theme)
    d.group("g_edge", "エッジ拠点 ※4", 40, 60, 300, 420)
    d.group("g_onprem", "オンプレミス", 40, 520, 300, 240)
    d.group("g_cellular", "セルラー接続（任意）※9", 40, 800, 300, 190)
    # The cloud starts at 500, not 380: the gap has to hold the widest inter-group edge
    # label, and "同期 / 読み取り配信" is ~140px wide.
    d.group("g_cloud", "AWS クラウド", 500, 60, 740, 980)

    d.icon("cam", "camera", "カメラ", 100, 110, uri("camera"), RESOURCE)
    d.icon("vib", "vibration", "振動センサー", 240, 110, uri("vibration"), RESOURCE)
    d.box("st", "ローカルストレージ", 90, 280, 200, 50)
    d.box("kc", "Kafka / ClickHouse", 90, 560, 200, 50)
    d.box("dash", "ダッシュボード", 90, 650, 200, 40)
    # Not edge equipment: SoracomIngestionRole is assumed by SORACOM's own AWS
    # account with the Operator ID as ExternalId, so the writer is their platform.
    # Drawn because this whole path was absent from the figure.
    d.box("soracom", "SORACOM プラットフォーム", 90, 870, 200, 50)

    # Storage spine, left to right, all centred on y=340 so the arrows are straight.
    d.icon("fsxn", "fsxn", "Amazon FSx for\nNetApp ONTAP", 550, 300, uri("fsxn"))
    d.icon("s3ap", "s3ap", "S3 Access Point\n※1 ※2", 720, 316, uri("s3ap"), RESOURCE)
    # Three consumers of the access point, fanned into their own rows.
    d.icon("bed", "bedrock", "Amazon Bedrock", 880, 110, uri("bedrock"))
    d.icon("ath", "athena", "Amazon Athena", 880, 300, uri("athena"))
    # Marked ※6: the AWS list of services with a published access-point walkthrough
    # covers Athena, Lambda, Glue, Bedrock Knowledge Bases, EMR Serverless, CloudFront
    # and Transfer Family. SageMaker AI is not on it, so an unqualified line from the
    # access point to it would read as a support claim this project cannot make.
    d.icon("sm", "sagemaker", "Amazon\nSageMaker AI ※8", 880, 500, uri("sagemaker"))
    # The icon package ships only a suite-level Quick icon; the node here is the BI
    # capability, which the docs call Amazon Quick Sight.
    d.icon("quick", "quick", "Amazon\nQuick Sight", 1030, 300, uri("quick"))
    # MQTT path, middle row. cloud/iot_ingestion/handler.py puts every object through
    # the access point — `Bucket=S3AP_ARN` at all three call sites, and its template
    # declares no bucket at all. This figure used to route it into a standard bucket.
    d.icon("iot", "iotcore", "AWS IoT Core", 550, 660, uri("iotcore"))
    d.icon("lam", "lambda", "AWS Lambda", 720, 660, uri("lambda"))
    # Cellular path, bottom row: cloud/ingestion/template.yaml, the one place a standard
    # bucket is real. Firehose delivers to DataLakeBucket and Glue crawls it.
    d.icon("kin", "kinesis", "Amazon Kinesis\nData Streams", 550, 900, uri("kinesis"))
    d.icon("fh", "firehose", "Amazon Data\nFirehose", 720, 900, uri("firehose"))
    d.icon("s3", "s3", "Amazon Simple\nStorage Service ※7", 880, 900, uri("s3"))
    d.icon("glue", "glue", "AWS Glue", 1050, 900, uri("glue"))

    d.edge("e1", "cam", "st", "NFS 書き込み", (0, 26, 0),
           exit=(1, 0.5), entry=(0.4, 0), points=[(170, 134)])
    # Lands at 0.3 rather than the middle of the side, which is where the sync line
    # arrives: two arrowheads on one point read as one arrow.
    d.edge("e2", "vib", "st",
           exit=(1, 0.5), entry=(1, 0.3), points=[(310, 134), (310, 295)])
    d.edge("e3", "vib", "kc", "イベント", (0, -8, 0),
           exit=(1, 0.9), entry=(1, 0.5), points=[(330, 153), (330, 585)])
    # One line with two heads: the edge both pushes new files up and reads cached data
    # back down, and two separate arrows here overlapped.
    d.edge("e4", "st", "fsxn", "同期 / 読み取り配信", (0, 0, -14),
           exit=(1, 0.7), entry=(0, 0.5), points=[(420, 315), (420, 340)], both=True)
    d.edge("e5", "kc", "dash")
    d.edge("e6", "fsxn", "s3ap", exit=(1, 0.5), entry=(0, 0.35))
    d.edge("e7", "s3ap", "bed",
           exit=(1, 0.25), entry=(0, 0.5), points=[(820, 328), (820, 150)])
    d.edge("e8", "s3ap", "ath", exit=(1, 0.5), entry=(0, 0.5))
    d.edge("e9", "s3ap", "sm",
           exit=(1, 0.75), entry=(0, 0.5), points=[(840, 352), (840, 540)])
    # Shifted 34px left: the midpoint of this line is x=675, which is exactly where the
    # PutObject riser below passes, and the label sat on top of it.
    d.edge("e10", "iot", "lam", "MQTT", (0, -34, -10), exit=(1, 0.5), entry=(0, 0.5))
    # Up the corridor between the file system and the access point, into the left side
    # of the access point below where the volume line arrives. Two arrowheads on one
    # point read as one arrow, hence 0.8 against e6's 0.35.
    d.edge("e11", "lam", "s3ap", "PutObject", (0, 34, 0),
           exit=(0, 0.5), entry=(0, 0.8), points=[(675, 700), (675, 354)])
    d.edge("e_soracom", "soracom", "kin", "テレメトリ", (0, 0, -10),
           exit=(1, 0.5), entry=(0, 0.5), points=[(420, 895), (420, 940)])
    d.edge("e12", "kin", "fh", exit=(1, 0.5), entry=(0, 0.5))
    d.edge("e15", "fh", "s3", exit=(1, 0.5), entry=(0, 0.5))
    d.edge("e16", "s3", "glue", exit=(1, 0.5), entry=(0, 0.5))
    # Enters Athena from above: the space below an icon belongs to its label. The riser
    # sits at 1200, clear to the right of both Glue and Quick.
    d.edge("e13", "glue", "ath",
           exit=(1, 0.5), entry=(0.5, 0), points=[(1200, 940), (1200, 270), (920, 270)])
    d.edge("e14", "ath", "quick", exit=(1, 0.5), entry=(0, 0.5))

    d.note(
        "note",
        [
            "補足",
            "※1 S3 Access Point は ONTAP 9.17.1 以降が必要",
            "同一リージョン・同一アカウント・マウント済みボリュームであること",
            "※2 認可は 2 層で評価される",
            "IAM とファイルシステム権限の両方を通る必要がある",
            "※4 実機テスト未完了",
            "エッジ側と ONTAP 連携は未検証",
            "※7 ここは標準の S3 バケットが必要",
            "Athena のクエリ結果の出力先は S3 バケットであることが公式に必須。"
            "Amazon Data Firehose の配信先も S3 バケット ARN で、access point を受けるかは未検証",
            "※8 S3 Access Point 経由の利用に公式手順がない",
            "公式手順があるのは Athena / AWS Lambda / AWS Glue / Bedrock Knowledge Bases / "
            "EMR Serverless / CloudFront / Transfer Family",
            "※9 この経路は任意で、既定では作られない",
            "SoracomOperatorId を指定したときだけ IAM ロールが作られる。SORACOM 側のアカウントが "
            "ExternalId 付きでそのロールを引き受け、Kinesis と S3 の raw/ 配下に書く",
        ],
        40, 1070, 1200, 215,
    )
    return d


def pattern01(uri, theme: str) -> Diagram:
    d = Diagram("pattern-01-edge-ai-bedrock", "Pattern 01", 1160, 830, theme)
    d.group("g_edge", "エッジ拠点 ※4", 40, 60, 300, 340)
    # 80px of clear air between the groups so the label on the line that crosses the
    # boundary sits in the gap instead of on a dashed border.
    d.group("g_cloud", "AWS クラウド", 420, 60, 680, 540)

    d.icon("cam", "camera", "カメラ", 100, 110, uri("camera"), RESOURCE)
    d.box("st", "ローカルストレージ", 90, 260, 200, 50)

    d.icon("fsxn", "fsxn", "Amazon FSx for\nNetApp ONTAP", 460, 140, uri("fsxn"))
    d.icon("s3ap", "s3ap", "S3 Access Point\n※3", 630, 156, uri("s3ap"), RESOURCE)
    d.icon("lam1", "lambda", "AWS Lambda", 810, 140, uri("lambda"))
    d.icon("bed1", "bedrock", "Amazon Bedrock", 980, 140, uri("bedrock"))
    # RESULT_BUCKET in the use-case templates is the shared stack's standard bucket,
    # and Athena reads the verdicts from it. Marked so the reader is not left to infer
    # that the access point could serve this and simply was not used.
    d.icon("s3", "s3", "Amazon Simple\nStorage Service ※7", 530, 420, uri("s3"))
    d.icon("lam2", "lambda", "AWS Lambda", 810, 420, uri("lambda"))
    d.icon("sns", "sns", "Amazon Simple\nNotification Service", 980, 420, uri("sns"))

    d.edge("e1", "cam", "st", "NFS 書き込み", (0, 26, 0),
           exit=(1, 0.5), entry=(0.4, 0), points=[(170, 134)])
    d.edge("e2", "st", "fsxn", "同期", (0, 0, -14),
           exit=(1, 0.5), entry=(0, 0.5), points=[(380, 285), (380, 180)])
    d.edge("e3", "fsxn", "s3ap", exit=(1, 0.5), entry=(0, 0.5))
    d.edge("e4", "s3ap", "lam1", "スクリーニング", (0, 0, -14),
           exit=(1, 0.5), entry=(0, 0.5))
    d.edge("e5", "lam1", "bed1", exit=(1, 0.5), entry=(0, 0.5))
    d.edge("e6", "lam1", "lam2", "詳細判定", (0, -40, 0),
           exit=(0, 0.85), entry=(0.5, 0), points=[(740, 208), (740, 380), (850, 380)])
    d.edge("e7", "lam2", "sns", "通知", (0, 0, -14), exit=(1, 0.5), entry=(0, 0.5))
    d.edge("e8", "lam2", "s3", "判定結果", (0, 0, -14), exit=(0, 0.5), entry=(1, 0.5))

    d.note(
        "note",
        [
            "補足",
            "※3 イベント通知は使えない",
            "ファイル到着の起点は FPolicy / 明示的な呼び出し / ポーリング",
            "※4 実機テスト未完了",
            "エッジ側と ONTAP 連携は未検証",
            "※7 ここは標準の S3 バケットが必要",
            "Athena のクエリ結果の出力先は S3 バケットであることが公式に必須。"
            "判定結果も現在は共有スタックのバケットに書いている",
        ],
        40, 640, 1060, 160,
    )
    return d


def pattern05(uri, theme: str) -> Diagram:
    d = Diagram("pattern-05-agentic-rag", "Pattern 05", 1080, 760, theme)
    d.group("g_onprem", "既存のファイル共有", 40, 60, 300, 300)
    # Width 600, not 560: the group has to contain the query riser at x=930 and the
    # label beside it, or the label crosses the boundary. Left edge at 420 leaves the
    # same 80px inter-group gap as the other figures.
    d.group("g_cloud", "AWS クラウド ※5", 420, 60, 600, 500)

    d.box("users", "利用者", 100, 110, 180, 40)
    d.box("docs", "文書", 100, 240, 180, 50)

    # Ingest across the top band, retrieval across the bottom one.
    d.icon("fsxn", "fsxn", "Amazon FSx for\nNetApp ONTAP", 460, 140, uri("fsxn"))
    d.icon("s3ap", "s3ap", "S3 Access Point", 630, 156, uri("s3ap"), RESOURCE)
    # Knowledge Bases by name: that is the integration AWS documents for an access
    # point, via the alias. Plain model invocation has no such walkthrough, and the
    # doc's own mermaid already said Knowledge Bases while this figure did not.
    d.icon("bed", "bedrock", "Amazon Bedrock\nKnowledge Bases", 810, 140, uri("bedrock"))
    d.icon("os", "opensearch", "Amazon OpenSearch\nService", 630, 380, uri("opensearch"))
    d.icon("agent", "agentcore", "Amazon Bedrock\nAgentCore", 810, 380, uri("agentcore"))

    d.edge("e1", "users", "docs", "NFS / SMB", (0, 40, 0))
    d.edge("e2", "docs", "fsxn", "同期", (0, 0, -14),
           exit=(1, 0.5), entry=(0, 0.5), points=[(380, 265), (380, 180)])
    d.edge("e3", "fsxn", "s3ap", exit=(1, 0.5), entry=(0, 0.5))
    d.edge("e4", "s3ap", "bed", "取り込み ※6", (0, 0, -14), exit=(1, 0.5), entry=(0, 0.5))
    # Leaves Bedrock sideways and comes back over the top of OpenSearch: a straight drop
    # would run through Bedrock's own label.
    d.edge("e5", "bed", "os", "ベクトルストア", (0, -56, 0),
           exit=(0, 0.9), entry=(0.5, 0), points=[(760, 212), (760, 340), (670, 340)])
    d.edge("e6", "agent", "os", "検索", (0, 0, -14), exit=(0, 0.5), entry=(1, 0.5))
    # Round the right-hand side rather than up the shared column, which holds both
    # icons' labels.
    d.edge("e7", "agent", "bed", "問い合わせ", (0, 44, 0),
           exit=(1, 0.25), entry=(1, 0.5), points=[(930, 400), (930, 180)])

    d.note(
        "note",
        [
            "補足",
            "※5 このリポジトリに実装なし",
            "AWS が公式手順を公開している",
            "※6 権限の非対称に注意",
            "単一の資格情報で全文書を取り込むと利用者ごとの区別が失われる",
        ],
        40, 600, 980, 130,
    )
    return d


DEFINITIONS = (overview, pattern01, pattern05)


def run_export(source: Path, target: Path, extra: list[str]) -> None:
    if not DRAWIO_BIN.is_file():
        print(f"  draw.io not found at {DRAWIO_BIN}; skipping export", file=sys.stderr)
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(  # nosec B603  # noqa: S603  fixed binary, no shell
        [str(DRAWIO_BIN), "--export", "--border", "12", *extra,
         "--output", str(target), str(source)],
        capture_output=True, text=True, check=False,
    )
    if not target.is_file() or target.stat().st_size == 0:
        print(result.stdout, result.stderr, file=sys.stderr)
        raise SystemExit(f"export produced nothing: {target}")
    # draw.io writes the SVG without a final newline; PNG is binary and left alone.
    if target.suffix == ".svg":
        body = target.read_bytes()
        if not body.endswith(b"\n"):
            target.write_bytes(body + b"\n")
    print(f"  {target.relative_to(REPO_ROOT)} ({target.stat().st_size // 1024} KB)")


def export_svg(source: Path, stem: str) -> None:
    """One SVG per figure, and it carries both themes.

    Left on the default theme, draw.io writes every colour as a CSS `light-dark()` pair
    plus `color-scheme: light dark`, so the viewer picks. Measured on these figures: 46
    such pairs, with #232F3E resolving to #bdc7d4 and #FFFFFF to #121212 under a dark
    scheme — a correct dark rendering of the light source, for free.

    That is also why there is no dark SVG. Exporting the dark palette this way inverts it
    the other way (#D5DBDB -> #2e3333), so serving a dark SVG to a dark-mode reader would
    hand them a light diagram. `--theme light|dark` pins the colours and would give a
    fixed pair, but one adaptive file is fewer artifacts and cannot be mismatched.
    """
    run_export(source, IMAGE_DIR / f"{stem}.svg", ["--format", "svg", "--embed-svg-images"])


def export_png(source: Path, stem: str) -> None:
    """PNG per figure per theme. A raster cannot adapt, so dark needs its own file.

    `--theme light` means "do not apply an inversion", not "make it light": the palette in
    the source decides. Without it the export depends on draw.io's default, which is how a
    dark source could silently come back light.
    """
    run_export(source, PNG_DIR / f"{stem}@2x.png",
               ["--format", "png", "--scale", "2", "--theme", "light"])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--icons", required=True, type=Path,
                        help="extracted AWS Architecture Icons package (keep outside the repo)")
    parser.add_argument("--export", action="store_true", help="also render SVG and PNG")
    args = parser.parse_args()

    if not args.icons.is_dir():
        raise SystemExit(f"icon package not found: {args.icons}")

    def uri(key: str) -> str:
        return data_uri(args.icons, key)

    seen: set[str] = set()
    # Only the light `.drawio` is committed. The dark one is the same definitions with a
    # different palette, so keeping it would be a second source of truth for one figure;
    # it is written to a temporary directory, exported and dropped.
    with tempfile.TemporaryDirectory(prefix="diagrams-dark-") as scratch:
        dark_dir = Path(scratch)
        for build in DEFINITIONS:
            for theme in THEMES:
                suffix = "" if theme == "light" else f"-{theme}"
                directory = DIAGRAM_DIR if theme == "light" else dark_dir
                diagram = build(uri, theme)
                seen.update(diagram.labels)

                ja_path = directory / f"{diagram.name}{suffix}.drawio"
                diagram.write(ja_path)
                english = translate(diagram)
                en_path = directory / f"{diagram.name}-en{suffix}.drawio"
                write_english(english._prebuilt, en_path)  # type: ignore[attr-defined]
                for path in (ja_path, en_path):
                    if theme == "light":
                        print(path.relative_to(REPO_ROOT))
                    else:
                        print(f"(scratch) {path.name}")

                if args.export:
                    for path, stem in ((ja_path, f"{diagram.name}{suffix}"),
                                       (en_path, f"{diagram.name}-en{suffix}")):
                        if theme == "light":
                            export_svg(path, stem)
                        export_png(path, stem)

    stray = [
        p for p in REPO_ROOT.rglob("*")
        if p.is_file() and re.match(r"(Arch_|Res_|Icon-package)", p.name)
        and ".venv" not in p.parts
    ]
    if stray:
        raise SystemExit(f"icon library files must not be committed: {stray[:5]}")

    # A mapping nothing uses is a mapping nobody maintains, and the next reader cannot
    # tell a stale entry from one whose figure is still to come.
    unused = sorted(set(LABELS) - seen)
    if unused:
        for label in unused:
            print(f"  unused LABELS entry: {label!r}", file=sys.stderr)
        raise SystemExit(f"{len(unused)} LABELS entr(ies) match no label in any figure")

    print(f"diagrams: OK ({len(seen)} distinct labels, {len(LABELS)} translated)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
