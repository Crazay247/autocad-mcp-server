"""Entry point for python -m autocad_arch_mcp."""

from .server import mcp


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
