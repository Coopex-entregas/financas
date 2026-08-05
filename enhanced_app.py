from pathlib import Path

_namespace = globals()
_parts_dir = Path(__file__).with_name("enhanced_parts")
for _part_name in ("part1.pyfrag", "part2.pyfrag", "part3.pyfrag", "part4.pyfrag", "part5.pyfrag"):
    _path = _parts_dir / _part_name
    exec(compile(_path.read_text(encoding="utf-8"), str(_path), "exec"), _namespace, _namespace)
