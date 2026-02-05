"""
Setup configuration for ContextMind
"""
from setuptools import setup, find_packages
from pathlib import Path

# Read README
readme_file = Path(__file__).parent / "README.md"
long_description = readme_file.read_text(encoding="utf-8") if readme_file.exists() else ""

# Read requirements
requirements_file = Path(__file__).parent / "requirements.txt"
requirements = []
if requirements_file.exists():
    with open(requirements_file, encoding="utf-8") as f:
        requirements = [line.strip() for line in f if line.strip() and not line.startswith("#")]

setup(
    name="contextmind",
    version="0.2.1",
    author="ContextMind Team",
    author_email="",
    description="A Multi-Mode Conversational AI Framework",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/Jasmine66Bloom/ContextMind",
    packages=find_packages(exclude=["tests", "examples", "docs", "resources", "logs"]),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Intended Audience :: Science/Research",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
    python_requires=">=3.8",
    install_requires=requirements,
    include_package_data=True,
    package_data={
        "contextmind": [
            "config/*.yaml",
            "modes/fnctod/*.yaml",
        ],
    },
    entry_points={
        "console_scripts": [
            "contextmind-cli=examples.cli_demo:main",
            "contextmind-web=examples.web_demo:main",
        ],
    },
    keywords="conversational-ai dialogue-system nlp multi-mode",
    project_urls={
        "Documentation": "https://github.com/Jasmine66Bloom/ContextMind/tree/main/docs",
        "Source": "https://github.com/Jasmine66Bloom/ContextMind",
        "Bug Reports": "https://github.com/Jasmine66Bloom/ContextMind/issues",
    },
)
