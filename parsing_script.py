import semver

MAX_PREFIX_INT_LENGTH = 16  # VARCHAR(16) in DB
MAX_PRERELEASE_WORD = "zzzzzzzzz"  # as last max possible word
MAX_PRERELEASE_WORD_LENGTH = (
    60  # VARCHAR(60) in DB: assuming max SemVer length is 64 minus X.Y.Z length
)

MAX_PRERELEASE_NUMBER = 999999999  # to support versions 999.999.999
MAX_PRERELEASE_NUMBER_LENGTH = 9  # len(INT-32)-1 as INT(32) in DB
PRERELEASE_INT_FACTOR = 1000

MAX_BUILD_WORD = "zzzzzzzzz"
MAX_BUILD_WORD_LENGTH = 60  # VARCHAR(60) in DB: assuming max SemVer length is 64 minus X.Y.Z length


def transform_version(_version: str) -> tuple:

    # TODO delete once Ok
    """
    transform_version(version) gives prefix, prerelease_word, prerelease_number, build, which we then use as follows:
    SELECT * FROM tf_module_version ORDER BY INET_ATON(SUBSTRING_INDEX(CONCAT(version_prefix,'.0.0.0'),'.',4)),
        prerelease_word, prerelease_number, version_build;
    """

    version_fully: str = _version.lstrip("v")

    ver = semver.parse(version_fully)
    prefix: str = str(ver["major"]) + "." + str(ver["minor"]) + "." + str(ver["patch"])
    prerelease = ver["prerelease"]
    build: str = ver["build"]

    prerelease_word: str
    prerelease_number: int

    prerelease_word, prerelease_number = parse_prerelease(prerelease)

    if prerelease_word == MAX_PRERELEASE_WORD and prerelease_number == -1:
        prerelease_number = MAX_PRERELEASE_NUMBER

    if build is None:
        build = MAX_BUILD_WORD
    else:
        if len(build) > MAX_BUILD_WORD_LENGTH:
            build = build[0:MAX_BUILD_WORD_LENGTH]

    return prefix, prerelease_word, prerelease_number, build


def parse_prerelease(prerelease: str) -> tuple:
    def is_number(symbol: str) -> bool:
        if "0" <= symbol <= "9":
            return True
        return False

    def cut_prerelease_word(_prerelease_word):
        if len(_prerelease_word) > MAX_PRERELEASE_WORD_LENGTH:
            _prerelease_word = _prerelease_word[0:MAX_PRERELEASE_WORD_LENGTH]
        return _prerelease_word

    prerelease_word: str = MAX_PRERELEASE_WORD
    prerelease_number: int

    if prerelease is None:
        return prerelease_word, -1

    try:
        # to support formats x.y.z-x.y.z
        ver_prerelease = semver.parse(prerelease)
        prerelease_number = int(
            int(str(ver_prerelease["major"])) * pow(PRERELEASE_INT_FACTOR, 2)
            + int(str(ver_prerelease["minor"])) * pow(PRERELEASE_INT_FACTOR, 1)
            + int(str(ver_prerelease["patch"]))
        )
        if prerelease_number > MAX_PRERELEASE_NUMBER:
            # it exceeds our limitations of allowed DB field
            # then go as usual by first appeared number
            raise ValueError
        return prerelease_word, prerelease_number
    except ValueError:
        pass

    j = 0
    while not is_number(prerelease[j]):
        if j == len(prerelease) - 1:
            prerelease_word = prerelease
            return cut_prerelease_word(prerelease_word), 0
        j += 1

    if j != 0:
        prerelease_word = prerelease[0:j]

    k = j
    while is_number(prerelease[k]):
        if k == len(prerelease) - 1:
            k += 1
            break
        k += 1

    prerelease_number_as_string: str = prerelease[j:k]
    if len(prerelease_number_as_string) > MAX_PRERELEASE_NUMBER_LENGTH:
        prerelease_number_as_string = prerelease[j : j + MAX_PRERELEASE_NUMBER_LENGTH]
    prerelease_number = int(prerelease_number_as_string)

    return cut_prerelease_word(prerelease_word), prerelease_number