from dotenv import load_dotenv
from getpass import getpass
import os
import requests
import xmltodict
import re


vendor_map = {
    'LENOVO': 986,
    'DELL': 179
}


def read_sku_map():
    file = open('sku_map.log', 'r')
    lines = file.readlines()
    file.close()

    map = {}

    for line in lines:
        tokens = line.split(' ')

        if len(tokens) > 1:
            map[tokens[0]] = tokens[1]

    return map


def dump_sku_map(sku_map):
    file = open('sku_map.log', 'w')

    for key, value in sku_map.items():
        file.write(f'{key} {value}\n')

    file.close()


def get_api_token(base, username, password):
    try:
        res = requests.post(f'{base}/auth/login', {
            'device_name': 'api',
            'username': username,
            'password': password
        })

        res.raise_for_status()

        return res.json()['token']
    except requests.exceptions.HTTPError:
        print('Login failed, try again')

        return None


def get_xml(url):
    try:
        res = requests.get(url)
        return xmltodict.parse(res.content)
    except:
        print('Failed to download XML file')
        return None


def get_laptop_brand(item):
    vendor = item['Vendor']

    if vendor in vendor_map:
        return vendor_map[vendor]
    
    return None


def parse_os(text):
    if 'Windows 11' in text:
        return 'Win 11'
    elif 'Windows 10' in text:
        return 'Win 10'
    elif 'macOS' in text:
        return 'Mac OS'
    elif 'Linux' in text:
        return 'Linux'
    else:
        return 'Ostalo'
    

def parse_cpu(text):
    if 'intel' in text.lower():
        return 'Intel'
    elif 'amd' in text.lower():
        return 'AMD'
    else:
        return 'Ostalo'
    

def parse_card(text):
    if text == 'Plug-in-Card':
        return 'Zasebna'
    
    return 'Integrisana'


def parse_display(text):
    result = re.findall(r'[\d]+[.\d]+', text)

    if len(result) > 0:
        res = result[0]

        if res == '13.4':
            return '13.3'
        
        return res
    
    return '15.6'


def parse_quantity(text):
    if text == '20+':
        return 20
    
    if text == '10+':
        return 10
    
    return text


def import_laptop(sku_map, price_map, url, api_token, item):
    code = item['ProductCode']
    if code in price_map:
        mode = 'insert'

        if code in sku_map:
            mode = 'update'

        price_obj = price_map[code]
        desc = item['ProductDescription']
        title = ' '.join(desc.split(',')[:2])

        if len(title) > 55:
            title = title[0:55]

        city_id = 131
        category_id = 39
        price = price_obj['RETAIL_PRICE']

        if price is None:
            price = 0

        price = float(price)
        price = round(price + (price * 0.17))
        
        available = False
        listing_type = 'sell'
        state = 'new'
        quantity = parse_quantity(price_obj['AVAIL'])
        sku_number = code
        brand_id = get_laptop_brand(item)
        display = '15.6'
        os = 'Ostalo'
        cpu = 'Ostalo'
        ram = '8 GB'
        card = 'Integrisana'
        
        if 'AttrList' not in item:
            return 0

        for attr in item['AttrList']['element']:
            if attr['@Name'] == 'Diagonal Length':
                display = parse_display(attr['@Value'])
            elif attr['@Name'] == 'Installed Operating System':
                os = parse_os(attr['@Value'])
            elif attr['@Name'] == 'CPU':
                cpu = parse_cpu(attr['@Value'])
            elif attr['@Name'] == 'Installed System Memory Storage Capacity':
                ram = attr['@Value']
            elif attr['@Name'] == 'Video Controller Form Factor':
                card = parse_card(attr['@Value'])

        payload = {
            'title': title,
            'description': desc,
            'price': price,
            'city_id': city_id,
            'category_id': category_id,
            'available': available,
            'listing_type': listing_type,
            'state': state,
            'quantity': quantity,
            'sku_number': sku_number,
            'brand_id': brand_id,
            'attributes': [{'id': 265, 'value': display}, {'id': 261, 'value': os}, {'id': 262, 'value': cpu}, {'id': 264, 'value': ram}, {'id': 3872, 'value': card}]
        }

        print(payload)

        if mode == 'insert':
            try:
                image_url = item['Image']
                image = requests.get(image_url, stream=True).raw
            except:
                print('Error loading image')
                return 0
        
        try:
            headers = {'Authorization': 'Bearer ' + api_token}

            if mode == 'insert':
                res = requests.post(f'{url}/listings', json=payload, headers=headers)

                id = res.json()['id']

                files = {'images[]': image}
                res = requests.post(f'{url}/listings/{id}/image-upload', headers=headers, files=files)
                requests.post(f'{url}/listings/{id}/publish', headers=headers)
                sku_map[code] = id
                
                return 1

            elif mode == 'update':
                id = sku_map[code]
                requests.put(f'{url}/listings/{id}', json=payload, headers=headers)

                return 1
        except Exception as e:
            print('API error')
            print(str(e))

            return 0
    
    else:
        return 0
            

def main():
    print('Loading environment...\n')
    load_dotenv()

    try:
        print('Loading SKU map\n')
        sku_map = read_sku_map()
    except:
        print('Failed to load SKU map\n')
        return

    url = os.getenv('OLX_API_URL')
    xml_products_url = os.getenv('TECHNOBIT_XML_PRODUCTS')
    xml_prices_url = os.getenv('TECHNOBIT_XML_PRICES')

    print('Reading XML...')

    products = get_xml(xml_products_url)
    prices = get_xml(xml_prices_url)

    if products is None or prices is None:
        return

    price_map = {}

    for price in prices['CONTENT']['PRICES']['PRICE']:
        price_map[price['WIC']] = price

    print('XML downloaded and parsed\n')

    username = input('Username: ')
    password = getpass('Password: ')

    api_token = get_api_token(url, username, password)

    if api_token is None:
        return;
    
    print('OLX Login success\n')

    counter = 0;

    for item in products['ProductCatalog']['Product']:
        if item['ProductType'] == 'Notebook - consumer' or item['ProductType'] == 'Notebook - commercial':
            try:
                counter += import_laptop(sku_map, price_map, url, api_token, item)
                print(f'{counter}\n')
            except:
                pass

    dump_sku_map(sku_map)


# Press the green button in the gutter to run the script.
if __name__ == '__main__':
    main()

