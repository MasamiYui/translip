from pathlib import Path

from video_voice_separate.models.cdx23_dialogue import (
    CDX23_BALANCED_WEIGHTS,
    CDX23_HIGH_QUALITY_WEIGHTS,
    Cdx23DialogueSeparator,
)


def test_cdx23_quality_to_weights(tmp_path: Path) -> None:
    balanced = Cdx23DialogueSeparator(quality="balanced", cache_dir=tmp_path)
    high = Cdx23DialogueSeparator(quality="high", cache_dir=tmp_path)
    assert balanced.weight_names == CDX23_BALANCED_WEIGHTS
    assert high.weight_names == CDX23_HIGH_QUALITY_WEIGHTS


def test_cdx23_download_uses_cache(tmp_path: Path, monkeypatch) -> None:
    downloaded: list[tuple[str, str]] = []

    def fake_download(url: str, destination: str) -> None:
        downloaded.append((url, destination))
        Path(destination).write_bytes(b"checkpoint")

    monkeypatch.setattr("torch.hub.download_url_to_file", fake_download)
    separator = Cdx23DialogueSeparator(quality="balanced", cache_dir=tmp_path)
    paths = separator.ensure_weights()
    assert len(paths) == 1
    assert paths[0].exists()
    assert downloaded
