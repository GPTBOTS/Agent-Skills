import zipfile

from skillpack.archive import write_zip


def test_write_zip_contents_and_determinism(tmp_path):
    entries = [("b.txt", b"two"), ("a/x.txt", b"one")]
    out1 = tmp_path / "one.zip"
    out2 = tmp_path / "two.zip"
    write_zip(entries, out1)
    write_zip(list(reversed(entries)), out2)  # different input order

    with zipfile.ZipFile(out1) as z:
        names = z.namelist()
        assert names == ["a/x.txt", "b.txt"]  # sorted
        assert z.read("a/x.txt") == b"one"

    # byte-identical regardless of input order
    assert out1.read_bytes() == out2.read_bytes()
