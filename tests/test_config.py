from __future__ import annotations

from pathlib import Path

import pytest

from shepherd import config
from shepherd.errors import ConfigError


def write(root: Path, text: str) -> None:
    (root / "shepherd.toml").write_text(text)


def touch(root: Path, *names: str) -> None:
    for name in names:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("module m; endmodule\n")


def test_load_valid(project: Path):
    cfg = config.load(project)
    assert cfg.board == "tangnano9k"
    assert cfg.top == "blinky"
    assert cfg.sources == ["rtl/blinky.v"]
    assert cfg.checks_ai is True


def test_missing_file(tmp_path: Path):
    with pytest.raises(ConfigError, match="no shepherd.toml"):
        config.load(tmp_path)


@pytest.mark.parametrize("missing", ["board", "top", "sources"])
def test_missing_required_key(tmp_path: Path, missing: str):
    keys = {"board": '"tangnano9k"', "top": '"t"', "sources": '["a.v"]'}
    del keys[missing]
    write(tmp_path, "\n".join(f"{k} = {v}" for k, v in keys.items()))
    pattern = f"'{missing}' is required" if missing != "sources" else "sources.*empty|adapters"
    with pytest.raises(ConfigError, match=pattern):
        config.load(tmp_path)


def test_invalid_toml(tmp_path: Path):
    write(tmp_path, "board = ")
    with pytest.raises(ConfigError, match="invalid TOML"):
        config.load(tmp_path)


def test_unknown_key_warns(project: Path):
    (project / "shepherd.toml").write_text(
        (project / "shepherd.toml").read_text() + 'colour = "blue"\n'
    )
    with pytest.warns(UserWarning, match="unknown key 'colour'"):
        config.load(project)


def test_find_project_root(project: Path):
    assert config.find_project_root(project / "rtl") == project.resolve()
    (project / "shepherd.toml").unlink()
    assert config.find_project_root(project / "rtl") != project.resolve()


def test_explicit_order_kept_and_globs_sorted(tmp_path: Path):
    touch(tmp_path, "z_top.v", "lib/b.v", "lib/a.v", "lib/c.sv")
    write(
        tmp_path,
        'board = "tangnano9k"\ntop = "t"\nsources = ["z_top.v", "lib/*.v", "lib/a.v", "lib/*"]\n',
    )
    cfg = config.load(tmp_path)
    names = [p.relative_to(tmp_path.resolve()).as_posix() for p in config.resolve_sources(cfg)]
    assert names == ["z_top.v", "lib/a.v", "lib/b.v", "lib/c.sv"]


def test_missing_source_file(tmp_path: Path):
    write(tmp_path, 'board = "tangnano9k"\ntop = "t"\nsources = ["nope.v"]\n')
    with pytest.raises(ConfigError, match="'nope.v' does not exist"):
        config.resolve_sources(config.load(tmp_path))


def test_glob_matching_nothing(tmp_path: Path):
    write(tmp_path, 'board = "tangnano9k"\ntop = "t"\nsources = ["rtl/*.v"]\n')
    with pytest.raises(ConfigError, match="matched no files"):
        config.resolve_sources(config.load(tmp_path))


def test_glob_ignores_state_dir(tmp_path: Path):
    touch(tmp_path, "a.v", ".shepherd/build/src/000_a.v")
    write(tmp_path, 'board = "tangnano9k"\ntop = "t"\nsources = ["**/*.v"]\n')
    sources = config.resolve_sources(config.load(tmp_path))
    assert [p.name for p in sources] == ["a.v"]


def test_constraints_autodetect(project: Path):
    cfg = config.load(project)
    assert config.resolve_constraints(cfg) == (project / "tangnano9k.cst").resolve()


def test_constraints_none(tmp_path: Path):
    touch(tmp_path, "a.v")
    write(tmp_path, 'board = "tangnano9k"\ntop = "t"\nsources = ["a.v"]\n')
    assert config.resolve_constraints(config.load(tmp_path)) is None


def test_constraints_ambiguous(project: Path):
    (project / "other.cst").write_text("")
    with pytest.raises(ConfigError, match="several constraint files"):
        config.resolve_constraints(config.load(project))


def test_constraints_explicit_missing(project: Path):
    (project / "shepherd.toml").write_text(
        (project / "shepherd.toml").read_text() + 'constraints = "missing.cst"\n'
    )
    with pytest.raises(ConfigError, match="'missing.cst' does not exist"):
        config.resolve_constraints(config.load(project))


def test_dump_round_trip(tmp_path: Path):
    write(
        tmp_path,
        'board = "tangnano9k"\ntop = "t"\nsources = ["a.v", "b \\"q\\".sv"]\n'
        'constraints = "x.cst"\n[adapters]\namaranth = { entry = "rtl/top.py:Top" }\n'
        "[checks]\nai = false\n",
    )
    cfg = config.load(tmp_path)
    write(tmp_path, config.dump(cfg))
    assert config.load(tmp_path) == cfg
