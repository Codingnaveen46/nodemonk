"""Extractor unit tests: python, js, go, rust, jvm, markdown, data."""

from __future__ import annotations

from pathlib import Path

from nodemonk.extract.python_ast import extract_python
from nodemonk.extract.javascript import extract_js
from nodemonk.extract.golang import extract_go
from nodemonk.extract.rust import extract_rust
from nodemonk.extract.jvm import extract_jvm
from nodemonk.extract.markdown import extract_markdown
from nodemonk.extract.datafile import extract_datafile


def test_python_nodes_and_edges(tmp_path: Path) -> None:
    p = tmp_path / "a.py"
    p.write_text(
        "import os\n"
        "from x.y import z\n"
        "class Alpha:\n"
        "    def go(self):\n"
        "        return helper()\n"
        "def helper():\n"
        "    return os.getpid()\n",
        encoding="utf-8",
    )
    bad = tmp_path / "bad.py"
    bad.write_text("def broken(:\n", encoding="utf-8")
    res = extract_python(p, "a.py")
    ids = {n["id"] for n in res["nodes"]}
    assert "file::a.py" in ids
    assert "a.py::Alpha" in ids
    assert "a.py::Alpha.go" in ids
    relations = {(e["source"], e["relation"]) for e in res["edges"]}
    assert ("file::a.py", "contains") in relations
    assert ("file::a.py", "imports") in relations
    res_bad = extract_python(bad, "bad.py")
    assert res_bad["nodes"] and res_bad["nodes"][0]["id"] == "file::bad.py"


def test_js(tmp_path: Path) -> None:
    p = tmp_path / "app.ts"
    p.write_text(
        "import { Router } from 'express'\n"
        "export class App extends Base { }\n"
        "export function main(): void { start(); Router(); }\n"
        "const helper = async (x: number) => x\n"
        "interface Config { a: number }\n",
        encoding="utf-8",
    )
    res = extract_js(p, "app.ts")
    ids = {n["id"] for n in res["nodes"]}
    assert "file::app.ts" in ids
    assert "app.ts::App" in ids
    assert "app.ts::main()" in ids
    rels = {e["relation"] for e in res["edges"]}
    assert "imports" in rels and "contains" in rels and "inherits" in rels


def test_go(tmp_path: Path) -> None:
    p = tmp_path / "svc.go"
    p.write_text(
        "package main\n"
        "import (\n"
        '    "net/http"\n'
        '    "github.com/x/y"\n'
        ")\n"
        "type Server struct{}\n"
        "func (s *Server) Start() error { serve() }\n"
        "func serve() {}\n",
        encoding="utf-8",
    )
    res = extract_go(p, "svc.go")
    ids = {n["id"] for n in res["nodes"]}
    assert "svc.go::Server" in ids
    assert "svc.go::serve" in ids
    has_module = any(e["relation"] == "imports" for e in res["edges"])
    assert has_module


def test_rust(tmp_path: Path) -> None:
    p = tmp_path / "lib.rs"
    p.write_text(
        "use std::collections::HashMap;\n"
        'pub mod utils;\n'
        "struct Server;\n"
        "trait Runnable { fn run(&self); }\n"
        "impl Runnable for Server { fn run(&self) {} }\n"
        "pub fn boot() { mongodb_connect(); }\n",
        encoding="utf-8",
    )
    res = extract_rust(p, "lib.rs")
    ids = {n["id"] for n in res["nodes"]}
    assert "lib.rs::Server" in ids
    assert any("mod::utils" in i for i in ids)
    rels = {e["relation"] for e in res["edges"]}
    assert "imports" in rels


def test_jvm_java(tmp_path: Path) -> None:
    p = tmp_path / "Main.java"
    p.write_text(
        "package com.acme;\n"
        "import java.util.List;\n"
        "public class Main extends Base implements Runnable {\n"
        "    public void run() {}\n"
        "    public static void main(String[] a) {}\n"
        "}\n",
        encoding="utf-8",
    )
    res = extract_jvm(p, "Main.java")
    ids = {n["id"] for n in res["nodes"]}
    assert "package::com.acme" in ids
    assert "Main.java::Main" in ids
    rels = {e["relation"] for e in res["edges"]}
    assert "imports" in rels
    assert any(e["relation"] == "inherits" for e in res["edges"])


def test_markdown_tree_and_links(tmp_path: Path) -> None:
    p = tmp_path / "doc.md"
    p.write_text(
        "# Title\n\nintro\n\n## Section A\n\nsee `src/x.py:3`\n\n## Section B\n\nsubpoint\n",
        encoding="utf-8",
    )
    res = extract_markdown(p, "doc.md")
    ids = {n["id"] for n in res["nodes"]}
    assert "file::doc.md" in ids
    assert any(i.endswith("::title") for i in ids)
    rels = {e["relation"] for e in res["edges"]}
    assert "section" in rels
    assert any(e["relation"] == "references" for e in res["edges"])


def test_datafile_json(tmp_path: Path) -> None:
    p = tmp_path / "conf.json"
    p.write_text('{"database": {"url": "x"}, "debug": true}', encoding="utf-8")
    res = extract_datafile(p, "conf.json", ".json")
    ids = {n["id"] for n in res["nodes"]}
    assert "file::conf.json" in ids
    assert any(i.endswith("::database") for i in ids)


def test_binary_asset_identity(tmp_path: Path) -> None:
    from nodemonk.extract.binaryasset import extract_binary

    p = tmp_path / "img.png"
    p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 40)
    res = extract_binary(p, "img.png", "image")
    assert res["nodes"][0]["file_type"] == "image"
