class MissingFile(Exception):
    def __init__(self, resource, path):
        self.resource = resource
        self.path = path

    def __str__(self):
        return (
                f"Could not find resource '{self.resource}' in directory"
                f" {self.path}."
               )
