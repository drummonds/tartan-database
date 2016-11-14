from ..core import Source, log, utils
import re
import requests
from PIL import Image

re_extract_ids = re.compile(
    'href="/tartan-ferret/display/([0-9]+)/[^"]*"',
    re.IGNORECASE
)

re_extract_attr = re.compile(
    '<span\s+class="infotype">\s*(.*?)\s*:?\s*</span>\s*'
    '<span\s+class="info">\s*(.*?)\s*</span>',
    re.IGNORECASE or re.UNICODE
)

# 'A'..'Z', '0-9'
catalogue_index = [chr(i) for i in range(ord('A'), ord('Z') + 1)] + ['0-9']

attr_map = {
    'Slog': 'slog',
    'Colour Sequence': 'color_sequence',
    'Name of Tartan': 'name',
    'Alternative Name': 'alt_name',
    'ITI Number': 'iti_number',
    'Category': 'category',
    'Designer / Source': 'designer',
    'Date': 'date',
    'Thread Count': 'threadcount',
    'Notes': 'notes',
}

re_normalize_threadcount = re.compile(
    '^([a-z]+)([0-9]+([a-z]+[0-9]+)+[a-z]+)([0-9]+)$',
    re.IGNORECASE
)

re_color_names = re.compile(
    '[a-z]+',
    re.IGNORECASE
)


def extract_colors(filename):
    result = []
    try:
        img = Image.open(filename).convert('RGB')
    except IOError:
        return None
    box = img.getbbox()
    if box is None:
        return None
    for x in range(0, box[2]):
        color = '#' + ''.join(map(
            lambda v: format(v, 'x').zfill(2),
            img.getpixel((x, 0))
        )).upper()

        if (len(result) == 0) or (result[-1] != color):
            result.append(color)
    return result


def build_palette(threadcount, colors):
    result = {}
    if (threadcount is None) or (colors is None):
        return result
    for index, name in enumerate(threadcount):
        if index >= len(colors):
            break
        result[name] = colors[index]

    return result


def normalize_threadcount(value, reflect=False):
    result = map(
        lambda v: re.sub('[^a-zA-Z0-9]+', '', v),
        value.split('.-.')
    )
    if reflect:
        result = map(
            lambda v: re.sub(re_normalize_threadcount, '\\1/\\2/\\4', v),
            result
        )

    result = map(
        lambda v: re.sub('([0-9]+)', '\\1 ', v).strip(),
        result
    )

    return ' // '.join(filter(len, result)).upper()


def parse_category(value, delimiter='; '):
    result = map(
        lambda v: v.title(),
        sorted(list(set(utils.extract_words(value))))
    )
    return delimiter.join(result)


def parse_metadata(data):
    result = map(
        lambda (key, value): (
            attr_map.get(key.strip().strip(':')),
            utils.cleanup(value)
        ),
        re_extract_attr.findall(data)
    )
    result = filter(
        lambda (key, value): key is not None,
        result
    )
    result = dict(result)

    if 'category' in result:
        result['category'] = parse_category(result['category'])

    if 'threadcount' in result:
        result['threadcount'] = normalize_threadcount(
            result.get('threadcount', ''),
            # AAA:BBB - reflective
            # ..ABC.. - repetitive
            ':' in result.get('slog', '')
        )
    else:
        result['threadcount'] = ''

    if 'designer' in result:
        if result['designer'].lower() == 'unknown':
            result['designer'] = ''

    return result


class TartansAuthority(Source):

    id = 'tartans_authority'
    name = 'Scottish Tartans Authority'

    folders = [
        'index',
        'grabbed',
        'images'
    ]

    headers = [
        ('source', 'Source'),
        ('id', 'Source ID'),
        ('name', 'Name'),
        ('alt_name', 'Alternative Name'),
        ('iti_number', 'ITI Number'),
        ('category', 'Category'),
        ('designer', 'Designer'),
        ('date', 'Date'),
        ('palette', 'Palette'),
        ('threadcount', 'Threadcount'),
        ('notes', 'Notes'),
        ('url', 'URL'),
    ]

    host = 'http://www.tartansauthority.com'
    username = 'pebox@stromox.com'
    password = 'q2222'

    url = 'http://www.tartansauthority.com/'

    session = None

    def get_session(self, force_new=False, prefix=''):
        if force_new or (self.session is None):
            session = requests.Session()
            session.headers.update({
                'User-Agent':
                    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
                    '(KHTML, like Gecko) Chrome/54.0.2840.59 Safari/537.36'
            })
            # Log in
            url = self.host + '/login'
            data = {
                'txtEmail': self.username,
                'txtPassword': self.password
            }
            resp = session.post(url, data=data)
            if resp.status_code == 200:
                log.notice(
                    prefix=prefix + 'Logged in',
                    message='as ' + self.username
                )
                self.session = session
            else:
                log.error(prefix=prefix + 'Failed', message='to log in')
                self.session = None
        return self.session

    def get_items(self):
        result = []

        # Iterate through all letters
        for letter in catalogue_index:
            url = self.host + '/tartan-ferret/tartans-a-to-z/'
            params = {'p': 'all', 'lt': letter}
            log.message('Loading ' + letter + '... ', suffix='')
            resp = requests.get(url, params=params)
            log.http_status(resp.status_code, resp.reason, suffix='')
            if resp.status_code == 200:
                self.file_put('index/' + letter + '.html', resp.content)
                ids = re_extract_ids.findall(resp.content)
                result += ids
                log.message(
                    ' found: ' + log.BOLD + str(len(ids)) + log.END + ' ID(s)',
                    suffix=''
                )
            log.newline()

        result = [x for x in result if int(x) > 0]
        return sorted(map(int, list(set(result))))

    def retrieve(self, item):
        id = str(item).zfill(6)
        log.message('Loading ' + str(item), suffix='...\n')
        # Image
        url = self.host + '/images/ferret/tartan_bars/' + id + '.png'
        resp = requests.get(url)
        log.http_status(resp.status_code, resp.reason, prefix='  image: ')
        if resp.status_code == 200:
            self.file_put('images/' + id + '.png', resp.content)

        url = self.host + '/tartan-ferret/display/' + str(item) + '/'
        session = self.get_session(prefix='  ')
        attempts = 5
        while attempts > 0:
            resp = session.get(url)
            log.http_status(resp.status_code, resp.reason, prefix='  page: ')
            if resp.status_code == 200:
                attr = re_extract_attr.findall(resp.content)
                is_page_valid = len(attr) > 0

                temp = dict(attr).get('Thread Count', '').lower()
                is_data_present = temp != 'available to sta members only'

                if is_page_valid:
                    if is_data_present:
                        return self.process_retrieved(
                            resp, 'grabbed/' + str(item).zfill(6) + '.html'
                        )
                    else:
                        session = self.get_session(True, prefix='  ')
            else:
                return self.process_retrieved(
                    resp, 'grabbed/' + str(item).zfill(6) + '.html'
                )
            attempts -= 1
            if attempts == 0:
                return self.SKIP, (item, resp.content)

    def extract_items(self, item):
        log.message('Parsing ' + str(item) + '...')
        filename = str(item).zfill(6)
        data = self.file_get('grabbed/' + filename + '.html')

        result = parse_metadata(data)

        result['source'] = self.name
        result['id'] = str(item)
        result['url'] = self.host + '/tartan-ferret/display/' + str(item) + '/'
        result['palette'] = ' '.join(map(
            lambda (key, value): key + value + ';',
            dict(build_palette(
                re_color_names.findall(result['threadcount']),
                extract_colors(self.realpath('images/' + filename + '.png'))
            )).items()
        ))

        return [result]