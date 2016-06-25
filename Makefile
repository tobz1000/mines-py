VENV_DIR = venv

all: $(VENV_DIR)

$(VENV_DIR):
	VENV_DIR=$(VENV_DIR) $(pwd)/setup/venv.sh

clean:
	rm -rf $(VENV_DIR)
