#!/usr/bin/env python3
"""Preserve EuroOffice FB2 conversion support when using the CryptPad recipe.

The original CryptPad x2t code disables FB2 entry points with return 0.
The allowlisted EuroOffice-first approach deliberately keeps them active,
so the final x2t link must see libFb2File.a built by the existing stage.
"""
import argparse
import pathlib
import sys


def modify(text):
    start = text.find('FROM base AS build\n')
    if start < 0:
        raise ValueError('Expected final build stage missing')
    before, build = text[:start], text[start:]
    marker = ('COPY --from=htmlfile2 /core/build/lib/linux_64/libHtmlFile2.a '
              '/core/build/lib/linux_64/\n')
    addition = ('COPY --from=fb2file /core/build/lib/linux_64/libFb2File.a '
                '/core/build/lib/linux_64/\n')
    if build.count(marker) != 1:
        raise ValueError('Expected HtmlFile2 library COPY in final build stage exactly once')
    if addition not in build:
        build = build.replace(marker, marker + addition, 1)
    return before + build


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('dockerfile')
    a = ap.parse_args()
    file = pathlib.Path(a.dockerfile)
    try:
        updated = modify(file.read_text())
        file.write_text(updated)
    except (ValueError, OSError) as exc:
        print('DOCKER RECIPE ERROR:', str(exc), file=sys.stderr)
        return 1
    print('PASS: final x2t link includes libFb2File.a without stubbing converter functionality')
    return 0


if __name__ == '__main__':
    sys.exit(main())
