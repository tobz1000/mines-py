VENV_DIR = venv

all: $(VENV_DIR)

$(VENV_DIR):
	VENV_DIR=$(VENV_DIR) ./setup/venv.sh

clean:
	rm -rf $(VENV_DIR)
