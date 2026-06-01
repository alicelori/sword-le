# Zenodo link : 
URL=https://zenodo.org/records/20398326/files/sword-le-test-data.zip?download=1

ZIP_FILE=data.zip

$(ZIP_FILE):
	@echo "Downloading dataset..."
	@curl -L $(URL) -o $(ZIP_FILE)
	@echo "Unzip dataset..."
	unzip -o $(ZIP_FILE)