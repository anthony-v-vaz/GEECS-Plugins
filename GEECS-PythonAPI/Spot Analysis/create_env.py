import subprocess
import sys
import venv

def create_virtual_environment(env_name):
    venv.create(env_name, with_pip=True)


def install_packages(env_name, requirements_file):
    subprocess.call([f"{env_name}/bin/pip", "install", "-r", requirements_file])


def main():
    if len(sys.argv) != 3:
        print("Usage: python create_env.py <environment_name> <requirements_file>")
        sys.exit(1)

    env_name = sys.argv[1]
    requirements_file = sys.argv[2]

    print(f"Creating virtual environment: {env_name}")
    create_virtual_environment(env_name)

    print(f"Installing packages from {requirements_file}")
    install_packages(env_name, requirements_file)

    print("Environment creation and package installation complete.")


if __name__ == "__main__":
    main()
