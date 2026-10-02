"""HTTP entry point; the application owns work after client disconnect."""

def create_app(*args, **kwargs):
    from .api import create_app as build
    return build(*args, **kwargs)

__all__ = ["create_app"]
