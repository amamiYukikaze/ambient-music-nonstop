"""Deterministic public CLAP bank; copy only text arrays without loading pickle."""
import argparse
import ast
import struct
import zipfile


def export(source, destination):
    with zipfile.ZipFile(source) as original, zipfile.ZipFile(destination, 'w') as public:
        for name in ('text_labels.npy', 'text_vectors.npy'):
            data = original.read(name)
            if data[:6] != b'\x93NUMPY':
                raise ValueError('Invalid NPY bank')
            major = data[6]
            if major not in (1, 2, 3):
                raise ValueError('Unsupported NPY version')
            size = 2 if major == 1 else 4
            length = struct.unpack('<H' if size == 2 else '<I', data[8:8 + size])[0]
            header = ast.literal_eval(data[8 + size:8 + size + length].decode('utf8'))
            if not isinstance(header['descr'], str) or 'O' in header['descr']:
                raise ValueError('Object arrays are not public data')
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            public.writestr(info, data)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source')
    parser.add_argument('destination')
    args = parser.parse_args()
    export(args.source, args.destination)
