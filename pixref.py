import absolute
import sys
import struct
import zlib
from dataclasses import dataclass
from io import BufferedReader
from math import ceil

# -- DATA DEFINITIONS --
@dataclass
class png_metadata:
    width: int
    height: int
    bitd: int
    colort: int
    compm: int
    filterm: int
    interlacem: int

@dataclass
class pixel:
    red: int
    green: int
    blue: int
    alpha: int

# -- GLOBALS --
DEBUG_MODE = False
mystack = absolute.glob() 
CHANNEL_LOOKUP = {0 : 1, 2 : 3, 3 : 1, 4 : 2, 6 : 4} # map colort to corresponding amount of channels

# -- HELPERS --
def read_chunk(file):
    chunk_len, chunk_type = struct.unpack(">I4s", file.read(8))
    chunk_data = file.read(chunk_len)
    checksum = zlib.crc32(chunk_data, zlib.crc32(struct.pack(">4s", chunk_type)))
    chunk_crc, = struct.unpack(">I", file.read(4))
    if chunk_crc != checksum:
        print(f"Problem: chunk checksum failed. {chunk_crc} != {checksum}. Exiting.")
        exit(1)
    return chunk_type, chunk_data

def uncompress_pixel_data(chunks):
     idat_data = b"".join(chunk_data for chunk_type, chunk_data in chunks if chunk_type == b"IDAT")
     idat_data = zlib.decompress(idat_data) # this line is an entire rabbit hole
     print(f"Check: length of uncompressed pixel data is {len(idat_data)}")
     return idat_data

def get_palette(chunks):
    plte_data = b"".join(chunk_data for chunk_type, chunk_data in chunks if chunk_type == b"PLTE")
    if not plte_data:
        print("Problem: no palette found for indexed color format. Exiting.")
        exit(1)
    return plte_data

# NOTE: the bit twiddling is very pythonic and doing it in C/asm would be harder. my bad.
def byte_array_to_bit_array_str(byte_array):
    bit_array = ""
    for byte in byte_array:
        bits = f"{byte:08b}"
        for bit in bits:
            bit_array += bit
    return bit_array

def group_bits(cluster_size, byte_array):
    bit_array = byte_array_to_bit_array_str(byte_array)
    grouped_bytes = []
    i = 0
    while i < len(bit_array):
        value = bit_array[i:i+cluster_size]
        grouped_bytes.append(int(value, 2))
        i+=cluster_size
    return grouped_bytes

def get_stride(idhr_fields):
	bits_per_pixel = CHANNEL_LOOKUP[idhr_fields.colort] * idhr_fields.bitd
	stride = ceil((idhr_fields.width * bits_per_pixel)/8)
	return stride

def paeth_predictor(a, b, c):
    p = a + b - c
    pa = abs(p - a)
    pb = abs(p - b)
    pc = abs(p - c)
    if pa <= pb and pa <= pc:
        pr = a
    elif pb <= pc:
        pr = b
    else:
        pr = c
    return pr

def left_pixel(unfilt, bytes_per_pixel, stride, r, c):
	return unfilt[int(r * stride + c - bytes_per_pixel)] if c >= bytes_per_pixel else 0

def top_pixel(unfilt, stride, r, c):
	return unfilt[int((r-1) * stride + c)] if r > 0 else 0

def top_left_pixel(unfilt, bytes_per_pixel, stride, r, c):
	return unfilt[int((r-1) * stride + c - bytes_per_pixel)] if r > 0 and c >= bytes_per_pixel else 0

def unfilter_pixel_data(idhr_fields, data):
	bits_per_pixel = CHANNEL_LOOKUP[idhr_fields.colort] * idhr_fields.bitd
	stride = ceil((idhr_fields.width * bits_per_pixel)/8)
	bytes_per_pixel = bits_per_pixel / 8

	unfilt = []
	i=0	

	for r in range(idhr_fields.height):
		filter_type = data[i]
		i+=1
		for c in range(stride):
			filter_x = data[i]
			i+=1
			if filter_type == 0:
				unfilt_x = filter_x
			elif filter_type == 1: # undo sub left
				unfilt_x = filter_x + left_pixel(unfilt, bytes_per_pixel, stride, r, c)
			elif filter_type == 2: # undo sub above
				unfilt_x = filter_x + top_pixel(unfilt, stride, r, c)
			elif filter_type == 3: # undo the subtraction of the average of the left and above
				term1 = left_pixel(unfilt, bytes_per_pixel, stride, r, c)
				term2 = top_pixel(unfilt, stride, r, c)
				unfilt_x = filter_x + (term1 + term2) // 2
			elif filter_type == 4: # undo subtraction of paeth magic
				unfilt_x = filter_x + paeth_predictor(
                                        left_pixel(unfilt, bytes_per_pixel, stride, r, c), 
                                        top_pixel(unfilt, stride, r, c), 
                                        top_left_pixel(unfilt, bytes_per_pixel, stride, r, c)
                                     )
			else: 
				print("Problem: unexpected filter type encountered. Exiting")
				exit()

			unfilt.append(unfilt_x & 0xff)
	return unfilt

# -- CONTROL FLOW --
def start_decode_png():
    global mystack
    
    fpath = mystack.pop()
    file = open(fpath, "rb")
    PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
    if file.read(len(PNG_SIGNATURE)) != PNG_SIGNATURE:
        print("Problem: invalid PNG signature. Exiting")
        exit(1)

    mystack.push(file)
    return read_all_chunks

def read_all_chunks():
    global mystack
    file = mystack.pop(enforce=BufferedReader)

    chunks = []
    while True:
        chunk_type, chunk_data = read_chunk(file)
        chunks.append((chunk_type, chunk_data))
        if chunk_type == b"IEND":
            break

    print("Chunks: ", [chunk_type for chunk_type, chunk_data in chunks])
    mystack.push(chunks)
    return parse_idhr_fields

def parse_idhr_fields():
    global mystack
    chunks = mystack.pop()
    _, ihdr_data = chunks[0]
    width, height, bitd, colort, compm, filterm, interlacem = struct.unpack(">IIBBBBB", ihdr_data)
    if colort not in (0, 2, 3, 4, 6):
        print("Problem: invalid color type. Exiting.")
        exit(1)
    print(f"Check: Width={width} Height={height}")

    idhr_fields = png_metadata(width, height, bitd, colort, compm, filterm, interlacem)
    mystack.push(idhr_fields)

    if compm != 0:
        print("Problem: invalid compression method. Exiting.")
        exit(1)
    if filterm != 0:
        print("Problem: invalid filter method. Exiting")
        exit(1)
    if interlacem != 0:
        print("TODO: interlacing is not currently supported. Exiting")
        exit()

    if colort not in (0, 2, 3, 4, 6):
        print("Problem: Unknown PNG format. Exiting.")
        exit(1)
    mystack.push(chunks)
    uncompress_and_defilter_data()

    match colort:
        case 0:
            print(f"colort={colort}, greyscale format detected")
            print(f"bitd={bitd}")
            if bitd not in (1, 2, 4, 8, 16):
                print("Problem: invalid bit depth. Exiting")
                exit(1)
            mystack.push(False)
            return get_image_greyscale
        case 2:
            print(f"colort={colort}, truecolor RGB format detected")
            print(f"bitd={bitd}")
            if bitd not in (8, 16):
                print("Problem: invalid bit depth. Exiting")
                exit(1)
            mystack.push(False)
            return get_image_rgb
        case 3:
            print(f"colort={colort}, indexed color format detected, searching for PLTE chunk...")
            print(f"bitd={bitd}")
            if bitd not in (1, 2, 4, 8):
                print("Problem: invalid bit depth. Exiting")
                exit(1)
            mystack.push(get_palette(chunks))
            return get_image_from_palette
        case 4:
            print(f"colort={colort}, greyscale format with alpha detected")
            print(f"bitd={bitd}")
            if bitd not in (8, 16):
                print("Problem: invalid bit depth. Exiting")
                exit(1)
            mystack.push(True)
            return get_image_greyscale
        case 6:
            print(f"colort={colort}, truecolor RGBA format detected")
            print(f"bitd={bitd}")
            if bitd not in (8, 16):
                print("Problem: invalid bit depth. Exiting")
                exit(1)
            mystack.push(True)
            return get_image_rgb

def uncompress_and_defilter_data():
    global mystack

    chunks = mystack.pop()
    idhr_fields = mystack.pop(enforce=png_metadata)
    uncom_pix_data = uncompress_pixel_data(chunks)

    stride = get_stride(idhr_fields)
    unfiltered_pixel_data = unfilter_pixel_data(idhr_fields, uncom_pix_data)
    mystack.push(idhr_fields)
    mystack.push(unfiltered_pixel_data)

def get_image_greyscale():
    global mystack
    alpha_present = mystack.pop()
    unfilt_data = mystack.pop()
    idhr_fields = mystack.pop(enforce=png_metadata)
    stride = get_stride(idhr_fields)
    
    # group bytes according to bit depth
    i=0
    greyscale = []
    for _ in range(idhr_fields.height):
        greyscale.append(group_bits(idhr_fields.bitd, unfilt_data[i:i+stride]))
        i+=stride

    max = (1 << idhr_fields.bitd) - 1
    print(f"Check: max intensity {max}")

    image = []
    if not alpha_present:
        for row in greyscale:
            scanline = []
            for grey in row:
                intensity = int((grey / max) * max)
                scanline.append(pixel(intensity, intensity, intensity, max))
            image.append(scanline)
    else:
        for row in greyscale:
            scanline = []
            for i in range(0, len(row), 2):
                intensity = row[i]
                alpha = row[i + 1]
                intensity = int((intensity / max) * max)
                scanline.append(pixel(intensity, intensity, intensity, alpha))
            image.append(scanline)

    mystack.push(max)
    mystack.push(image)
    return plot_image

def get_image_rgb():
    global mystack
    alpha_present = mystack.pop()
    unfilt_data = mystack.pop()
    idhr_fields = mystack.pop(enforce=png_metadata)
    stride = get_stride(idhr_fields)
    max = (1 << idhr_fields.bitd) - 1

    rgb = []
    image = []
    i=0
    if not alpha_present:
        for _ in range(idhr_fields.height):
            scanline = []
            row = group_bits(idhr_fields.bitd, unfilt_data[i:i+stride])
            for j in range(0, len(row), 3):
                pix = row[j:j+3]
                scanline.append(pixel(pix[0], pix[1], pix[2], max))
            image.append(scanline)
            i+=stride
    else:
        for _ in range(idhr_fields.height):
            scanline = []
            row = group_bits(idhr_fields.bitd, unfilt_data[i:i+stride])
            for j in range(0, len(row), 4):
                pix = row[j:j+4]
                scanline.append(pixel(pix[0], pix[1], pix[2], pix[3]))
            image.append(scanline)
            i+=stride

    mystack.push(max)
    mystack.push(image)
    return plot_image

def get_image_from_palette():
    global mystack
    palette_data = mystack.pop()
    unfilt_data = mystack.pop()
    idhr_fields = mystack.pop(enforce=png_metadata)
    stride = get_stride(idhr_fields)
    max = 255 # palette doesnt support transparency, just hardcode to 255
    print(f"max: {max}")

    grouped_palette = group_bits(8, palette_data)
    palette = []
    for i in range(0, len(grouped_palette), 3):
        palette.append(grouped_palette[i:i+3])

    # group bytes according to bit depth
    i=0
    indices = []
    for _ in range(idhr_fields.height):
        indices.append(group_bits(idhr_fields.bitd, unfilt_data[i:i+stride]))
        i+=stride

    image = []
    for row in indices:
        scanline = []
        for index in row:
            color = palette[index]
            scanline.append(pixel(color[0], color[1], color[2], max))
        image.append(scanline)

    mystack.push(max)
    mystack.push(image)
    return plot_image

# very lazy and slow!!
import numpy as np
import matplotlib.pyplot as plt
def plot_image():
    image = mystack.pop()
    max = mystack.pop()
    array = np.array([[[pix.red, pix.green, pix.blue, pix.alpha] for pix in row] for row in image])
    array = array / max
    plt.imshow(array)
    plt.axis("off")
    plt.show()

# -- LAUNCH PROGRAM AND DEBUG HELP --
try:
    mystack.push(sys.argv[1])
except IndexError:
    print("Problem: no file given. Exiting.")
    exit(1)

current = start_decode_png

if DEBUG_MODE:
    mystack.trace(current)
while current:
    current = current()
    if DEBUG_MODE:
        mystack.trace(current)
if DEBUG_MODE:
    print("Exiting.")

