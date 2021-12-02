# semver-sort-py-sql
Sorting tool for semantic versions

This repo is about how to sort semantic versions in SQL. 

By Semantic Versioning 2.0.0 format X.Y.Z Semantic Versioning 2.0.0: V1.10.1 or V1.2.0.

Usual SemVer sorting 
```
for module, versions in result.items():
    result[module] = sorted(
        versions, key=lambda x: mixutil.SemVersion(x.version), reverse=True
    )
```
doesn’t support a proper prerelease sorting a proper sorting for formats vX.Y.Z-prerelease+build, so 1.0.0-beta2 < 1.0.0-beta10 will be screed up.

SQL itself doesn't support a proper sorting as well. But there is a solution as follows:

**SELECT * FROM module_version ORDER BY INET_ATON(SUBSTRING_INDEX(CONCAT(version,'.0.0.0'),'.',4));** - we are sorting on a function of the column, rather than on the column itself, we cannot use an index on the column to help with the sort. In other words, the sorting will be relatively slow. But we are not using indexes on these columns, assuming a lot of versions are duplicated for different modules/images.

The query above works good with formats X.Y.Z, but it doesn’t work with vX.Y.Z-prerelease+build. 

To support that kind of cases, we have to split prerelease and build on different columns and do sorting.
To work around that we can use the following queery:

```
SELECT * FROM table_of_versions ORDER BY
    INET_ATON(
        SUBSTRING_INDEX(
            CONCAT(
                SUBSTRING_INDEX(
                    SUBSTRING_INDEX(version, '+', 1), '-', 1),'.0.0.0')
                ,'.',4)
            ),
    IF(
        LENGTH(version) = LENGTH(SUBSTRING_INDEX(SUBSTRING_INDEX(SUBSTRING_INDEX(version, '+', 1), '-', 2), '-', -1)),
            "~", SUBSTRING_INDEX(
                    SUBSTRING_INDEX(
                        SUBSTRING_INDEX(version, '+', 1), '-', 2), '-', -1)
    ) DESC,
    SUBSTRING_INDEX(
        SUBSTRING_INDEX(version, '+', 2), '+', -1);
```

Py peewee implementation:
```
def SUBSTRING_INDEX(
    expression: tp.Union[str, peewee.SQL], delimiter: str, count: int
) -> peewee.SQL:
    """String implementing SUBSTRING_INDEX SQL function only for MySQL"""
    if isinstance(expression, peewee.SQL):
        expression = expression.sql
    return peewee.SQL(f"SUBSTRING_INDEX({expression}, {delimiter}, {count})")


def ORDER_BY_SEMVER(version_field_name: str, direction: tp.Optional[str] = "ASC") -> list:
    """
        Implementing SemVer sorting through MySQL.
        The function splits semver onto 3 parts: X.Y.Z, prerelease and build.
        Then, sort query is built in order X.Y.Z, prerelease and build.
        If version hasn't prerelease, we treat it with prerelease = '~' to
        follow 1.0.0-alpha < 1.0.0.
        Take a note that 1.0.0+build2021 < 1.0.0-alpha, which doesn't follow SemVer
    """
    xyz_prerelease_part_sql = SUBSTRING_INDEX(version_field_name, "'+'", 1)
    build_part_sql = SUBSTRING_INDEX(SUBSTRING_INDEX(version_field_name, "'+'", 2), "'+'", -1)
    xyz_part_sql = SUBSTRING_INDEX(xyz_prerelease_part_sql, "'-'", 1)
    prerelease_part_sql = SUBSTRING_INDEX(
        SUBSTRING_INDEX(xyz_prerelease_part_sql, "'-'", 2), "'-'", -1
    )

    concat = peewee.fn.CONCAT(f"{xyz_part_sql.sql},'.0.0.0'")
    concat_build = f"{concat.name}({concat.arguments[0]})"

    major_minor_patch_order_by = peewee.Ordering(
        peewee.fn.INET_ATON(SUBSTRING_INDEX(concat_build, "'.'", 4)), direction,
    )

    # if format is only X.Y.Z, we assign it as '~' to follow semver sorting
    prerelease_query = peewee.SQL(
        "IF("
        f"LENGTH({version_field_name}) = LENGTH({prerelease_part_sql.sql}), "
        f"'~', {prerelease_part_sql.sql})"
    )

    prerelease_order_by = peewee.Ordering(prerelease_query, direction,)

    build_order_by = peewee.Ordering(build_part_sql, direction,)

    order_by = [major_minor_patch_order_by, prerelease_order_by, build_order_by]

    return order_by


def main():
    
    sort_criteria = [("version", "DESC"), ("created_at", "DESC")]
    query = model.select()
    
    for i, criteria in enumerate(sort_criteria):
        if criteria.node.name == "version":  # sort by semver
            semver_order_by = ORDER_BY_SEMVER(
                criteria.node.name, criteria.direction
            )
            sort_criteria.remove(criteria)
            for j, order_by in enumerate(semver_order_by):
                sort_criteria.insert(i + j, order_by)
            break

    query = query.order_by(*sort_criteria)
    
    result = []
    for raw in query:
        result.append(raw)
```

That works fine, but 1.0.0+build < 1.0.0 and 1.0.0-aplha not always smaller that 1.0.0-alpha2.

Another way - we can fulfil additional columns prerelease and build for a proper semver sorting.
Then, prerelease can contain various numbers in formats like X.Y.Z-wordNumber+build like v1.2.3-alpha10. To do a proper sorting and to support 1.0.0-alpha < 1.0.0-alpha.1 < 1.0.0-alpha.beta < 1.0.0-beta < 1.0.0-beta.2 < 1.0.0-beta.11 < 1.0.0-rc.1 < 1.0.0 we have to split prerelease onto 2 columns word and number.

                                                        V1.10.1-alpha10+build2001231

                                               /                     \                   \

                                              1.10.1               alpha10          build2001231

                                                                  /        \

                                                                 alpha      10

Once we added 4 new columns: 
``version_prefix`` to hold ``1.10.1``, ``prerelease_word`` - ``alpha``,  ``prerelease_number`` - ``10``,  ``version_build`` - ``build2001231``,
we can ask SQL as:

```
SELECT * FROM table_version ORDER BY INET_ATON(SUBSTRING_INDEX(CONCAT(version_prefix,'.0.0.0'),'.',4)), prerelease_word, prerelease_number, version_build;
```


To satisfy a property ``1.0.0-alpha < 1.0.0 & 1.0.0-1 < 1.0.0``, we have to fill up the new fields accordingly as shown on the picture below:

![Picture](https://github.com/kotsky/semver-sort-py-sql/blob/main/pics/initial_table.png)

Once we apply the query above, we get:

![Picture](https://github.com/kotsky/semver-sort-py-sql/blob/main/pics/sorted_table.png)

To help to split initial semantic version vX.Y.Z-prerelease-build, [python script]((https://github.com/kotsky/semver-sort-py-sql/blob/master/parsing_script.py)) is presented.
