from __future__ import annotations

from dataclasses import asdict, dataclass

from backend.version import __version__


@dataclass(frozen=True)
class ComponentLicense:
    id: str
    name: str
    version: str
    url: str
    sha256: str


@dataclass(frozen=True)
class ComponentDescriptor:
    id: str
    name: str
    version: str
    protocol_version: int
    platform: str
    architecture: str
    asset_name: str
    executable: str
    release_tag: str
    license: ComponentLicense
    model_id: str
    model_revision: str
    devices: tuple[str, ...] = ("cpu",)

    def as_dict(self) -> dict[str, object]:
        result = asdict(self)
        result["devices"] = list(self.devices)
        return result


DINOV3_LICENSE = ComponentLicense(
    id="dinov3-license",
    name="DINOv3 License",
    version="2025-08-19",
    url=(
        "https://huggingface.co/facebook/dinov3-vits16-pretrain-lvd1689m/"
        "blob/main/LICENSE.md"
    ),
    sha256="25d122eb8f5b880fd23c736fb6ea8018ee45c12237e00b8a86d14c653904999e",
)

DINOV3_COMPONENT = ComponentDescriptor(
    id="dinov3-cpu",
    name="DINOv3 CPU 特征提取组件",
    version="0.1.0",
    protocol_version=1,
    platform="ubuntu24.04",
    architecture="amd64",
    asset_name=(
        "automation-toolbox-provider-dinov3-cpu_0.1.0_"
        "ubuntu24.04_amd64.tar.gz"
    ),
    executable="automation-toolbox-provider-dinov3",
    release_tag=f"v{__version__}",
    license=DINOV3_LICENSE,
    model_id="facebook/dinov3-vits16-pretrain-lvd1689m",
    model_revision="2e601320d0545509ab03374e2f8707f303e1de7a",
)

BUILTIN_COMPONENTS = {DINOV3_COMPONENT.id: DINOV3_COMPONENT}

