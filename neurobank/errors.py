class MissingFileError(Exception):
    def __init__(self, resource, path):
        self.resource = resource
        self.path = path

    def __str__(self):
        return (
                f"Could not find resource '{self.resource}' in directory"
                f" {self.path}."
               )


class NotAFileError(Exception):
    def __init__(self, resource, path):
        self.resource = resource
        self.path = path

    def __str__(self):
        return (
                f"Resource '{self.resource}' was found in directory"
                f" {self.path}, but it is not a file, so it cannot be"
                " downloaded"
               )
