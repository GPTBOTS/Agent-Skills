from skillpack.config import Limits
from skillpack.limits import check_limits
from skillpack.source import load_source


def codes(problems):
    return [p.code for p in problems]


def test_within_limits_no_problems(make_skill):
    src = load_source(make_skill())
    assert check_limits(src, Limits()) == []


def test_total_size_exceeded(make_skill):
    src = load_source(make_skill(extra={"big.bin": b"x" * 2048}))
    limits = Limits(max_total_size_mb=0)  # 0 MB -> any content exceeds
    problems = check_limits(src, limits)
    assert "E007" in codes(problems)
    assert any(p.level == "error" for p in problems if p.code == "E007")


def test_file_count_warns(make_skill):
    src = load_source(make_skill(extra={f"f{i}.txt": "x" for i in range(3)}))
    problems = check_limits(src, Limits(max_file_count=2))
    assert "W005" in codes(problems)


def test_skill_md_too_big_warns(make_skill):
    src = load_source(make_skill(body="x" * 100))
    problems = check_limits(src, Limits(max_skill_md_bytes=10))
    assert "W005" in codes(problems)
