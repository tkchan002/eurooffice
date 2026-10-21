#!/usr/bin/env python3
"""Adapt the pinned CryptPad x2t Dockerfile for EuroOffice 9.3.5.

CryptPad 95f775f defines an `html` stage which runs core/Common/3dParty/html/fetch.py.
That fetch.py pins Gumbo and Katana source, whose .pri files list their C files
as direct project SOURCES. It does not define `gumbo` or `katana` Docker stages.

The original upstream recipe mistakenly references those names as external
image names. This patch reuses the existing pinned `html` stage for the FB2
parser source, drops two unused .a COPYs from the optional log-symbols stage,
and retains EuroOffice's FB2 converter at final link time.

All edits are specific to the verified upstream layout and fail closed.
"""
import argparse
from pathlib import Path
import sys

FB2_STAGE = 'FROM base AS fb2file\n'
LOG_STAGE = 'FROM base AS log-symbols\n'
BUILD_STAGE = 'FROM base AS build\n'
OLD_FB2_PARSER = 'COPY --from=gumbo /gumbo-parser /gumbo-parser\n'
NEW_FB2_PARSER = ('COPY --from=html /core/Common/3dParty/html '
                  '/core/Common/3dParty/html\n')
OLD_GUMBO_ARCHIVE = ('COPY --from=gumbo /usr/local/lib/libgumbo.a '
                     '/core/build/lib/linux_64/\n')
OLD_KATANA_ARCHIVE = ('COPY --from=katana /usr/local/lib/libkatana.a '
                      '/core/build/lib/linux_64/\n')
HTML_PROJECT_NOTE = (
    '# Gumbo/Katana are compiled from the pinned html stage source by their\n'
    '# respective .pri project files; no standalone libgumbo/libkatana stage.\n'
)
HTMLFILE2_MARKER = ('COPY --from=htmlfile2 /core/build/lib/linux_64/libHtmlFile2.a '
                    '/core/build/lib/linux_64/\n')
FB2_LIB = ('COPY --from=fb2file /core/build/lib/linux_64/libFb2File.a '
           '/core/build/lib/linux_64/\n')


def between(text, start, end):
    if text.count(start) != 1 or text.count(end) != 1:
        raise ValueError(f'Expected exactly one {start.strip()} and {end.strip()} stage')
    a = text.index(start) + len(start)
    b = text.index(end, a)
    return text[:a], text[a:b], text[b:]


def modify(text):
    # This build stage is the only required consumer of the original /gumbo-parser.
    if text.count('FROM base AS html\n') != 1:
        raise ValueError('Pinned Dockerfile must contain exactly one html fetch stage')
    if text.count('RUN python fetch.py\n') == 0:
        raise ValueError('Pinned html stage must fetch the parser sources')
    head, fb2, tail = between(text, FB2_STAGE, 'FROM base AS htmlfile2\n')
    if fb2.count(OLD_FB2_PARSER) == 1 and fb2.count(NEW_FB2_PARSER) == 0:
        fb2 = fb2.replace(OLD_FB2_PARSER, NEW_FB2_PARSER, 1)
    elif fb2.count(OLD_FB2_PARSER) == 0 and fb2.count(NEW_FB2_PARSER) == 1:
        pass  # already patched
    else:
        raise ValueError('Unexpected FB2 Gumbo parser COPY; review the pinned Dockerfile')
    text = head + fb2 + tail

    head, logs, tail = between(text, LOG_STAGE, 'FROM scratch AS log-symbols-output\n')
    if logs.count(OLD_GUMBO_ARCHIVE) == 1 and logs.count(OLD_KATANA_ARCHIVE) == 1:
        logs = logs.replace(OLD_GUMBO_ARCHIVE + OLD_KATANA_ARCHIVE,
                            HTML_PROJECT_NOTE, 1)
    elif (OLD_GUMBO_ARCHIVE not in logs and OLD_KATANA_ARCHIVE not in logs
          and logs.count(HTML_PROJECT_NOTE) == 1):
        pass  # already patched
    else:
        raise ValueError('Unexpected Gumbo/Katana archive COPYs in optional log-symbols stage')
    text = head + logs + tail

    head, build = text.split(BUILD_STAGE, 1) if text.count(BUILD_STAGE) == 1 else (None, None)
    if head is None:
        raise ValueError('Expected exactly one final x2t build stage')
    if build.count(HTMLFILE2_MARKER) != 1:
        raise ValueError('Expected exactly one HtmlFile2 library COPY in final build stage')
    if build.count(FB2_LIB) == 0:
        build = build.replace(HTMLFILE2_MARKER, HTMLFILE2_MARKER + FB2_LIB, 1)
    elif build.count(FB2_LIB) != 1:
        raise ValueError('Unexpected duplicate Fb2File archive COPY')
    text = head + BUILD_STAGE + build
    if '--from=gumbo' in text or '--from=katana' in text:
        raise ValueError('Undefined Gumbo/Katana external-image references remain')
    return text


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('dockerfile')
    a = ap.parse_args()
    path = Path(a.dockerfile)
    try:
        original = path.read_text(encoding='utf-8')
        patched = modify(original)
        if patched != original:
            path.write_text(patched, encoding='utf-8')
    except (ValueError, OSError) as exc:
        print(f'DOCKER RECIPE ERROR: {exc}', file=sys.stderr)
        return 1
    print('PASS: FB2 uses pinned HTML parser sources, undefined Gumbo/Katana stages removed, FB2 linked')
    return 0


if __name__ == '__main__':
    sys.exit(main())
