import hashlib
from pathlib import Path


def _hash(fp: Path, block_size=65536):
    # Create the hash object, can use something other than `.sha256()` if you wish
    file_hash = hashlib.sha256()

    # Open the file to read it's bytes
    with fp.open('rb') as f:
        # Read from the file. Take in the amount declared above
        fb = f.read(block_size)

        # While there is still data being read from the file
        while len(fb) > 0:
            # Update the hash
            file_hash.update(fb)

            # Read the next block from the file
            fb = f.read(block_size)

    # Get the hexadecimal digest of the hash
    return file_hash.hexdigest()


if __name__ == "__main__":
    """
    Checks if the o
    """

    # Set the reference AUSTAL folder
    _ref = Path(__file__).parents[1] / 'example' / 'testing_ref'

    # Set the generated AUSTAL folder
    _new = Path(__file__).parents[1] / 'example' / 'testing'

    # Get a list of files relative to the parent folder
    _ref_files = sorted(x.relative_to(_ref) for x in _ref.glob('**/*'))
    _new_files = sorted(x.relative_to(_new) for x in _new.glob('**/*'))

    # Check if the list of files is equal
    assert _ref_files == _new_files

    # Check if each file is equal
    for f in _ref_files:
        _ref_f = _ref / f
        if _ref_f.is_file():
            _ref_hash = _hash(_ref_f)
            _new_hash = _hash(_new / f)
            assert _ref_hash == _new_hash, _ref_f
