from setuptools import setup

PACKAGES = [
    "brain_langchain",
    "brain_langchain.api_manager",
    "brain_langchain.api_manager.api_handler",
]

setup(
    name="brain-langchain",
    version="1.0.0",
    description="Failover-aware LangChain chat model (Brain / call_api stack)",
    package_dir={"brain_langchain": "."},
    packages=PACKAGES,
    include_package_data=True,
    install_requires=[
        "langchain-core>=0.2.0",
        "requests>=2.31.0",
        "pydantic>=2.0",
        "python-dotenv>=1.0.0",
    ],
    python_requires=">=3.9",
    zip_safe=False,
)