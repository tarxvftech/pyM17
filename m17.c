#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <arpa/inet.h>
/*
240b: Full LICH without sync:
        48b  Address dst
        48b  Address src
        16b  int(M17_Frametype)
        128b nonce (for encryption)
    16b  Frame number counter
    128b payload
    16b  CRC-16 chksum
*/

//all structures must be big endian on the wire, so you'll want htonl (man byteorder 3) and such. 
typedef struct _LICH {
	uint8_t  addr_dst[6]; //48 bit int - you'll have to assemble it yourself unfortunately
	uint8_t  addr_src[6];  
	uint16_t frametype; //frametype flag field per the M17 spec
	uint8_t  nonce[16]; //bytes for the nonce
} M17_LICH; 
//without SYNC or other parts

typedef struct _ip_frame {
	M17_LICH lich;		
	uint16_t framenumber;	
	uint8_t  payload[16]; 	
	uint8_t  crc[2]; 	//16 bit CRC

} M17_IPFrame;
void m17_set_addr(uint8_t * dst, uint64_t address){
	for( int i = 0,j=5; i < 6 ; i++, j--){
		dst[j] = (address>>(i*8)) & 0xff;
		/*
		bbbbbb = iiii iiii
		     ^           ^
		   <<|         <<| 
		     -------------
		*/
	}
}
void init_lich(M17_LICH * x,
		uint64_t dst,
		uint64_t src,
		uint16_t frametype,
		char * nonce
		){
	uint8_t *y = (uint8_t *) x;
	memset(y, 0, sizeof(M17_LICH));
	m17_set_addr(x->addr_src, src);
	m17_set_addr(x->addr_dst, dst);
	x->frametype = htons(frametype);
	memset(x->nonce, *nonce, 16);
}
void init_frame(M17_IPFrame * x,
		uint64_t dst,
		uint64_t src,
		uint16_t frametype,
		char *   nonce,
		uint16_t framenumber,
		uint8_t* payload
		){
	uint8_t *y = (uint8_t *) x;
	memset(y, 0, sizeof(M17_IPFrame));
	init_lich(&x->lich, dst,src,frametype,nonce);
	x->framenumber = htons(framenumber);
	memcpy(x->payload, payload, 16);
	x->crc[0] = 0xff;
	x->crc[1] = 0xff;
}
void print_frame(M17_IPFrame * x){
	uint8_t *y = (uint8_t *) x;
	printf("0x41 == nonce\n0x42 == payload\n");
	printf("           destination         source       type (16 bits)\n");
	printf("        _________________ _________________ _____\n");
	for( int i = 0; i < sizeof(M17_IPFrame); i++){
		if( i == 32 ) printf("<- frame number, uin16");
		if( i>0 && i %16 == 0){ printf("\n"); }
		if(i%16==0){ printf("0x%04x  ",i); }
		printf("%02x ", y[i]);
		if( i == 49 ) printf("<- CRC16");
	}
}
int main(int argc, char **argv){
	M17_IPFrame x;
	init_frame(&x, 
			0x000000C4CC5E,
			0x00000161AE1F,
			5, //voice stream
			"AAAAAAAAAAAAAAAA", //mark out the nonce clearly
			13, //just as an example
			"BBBBBBBBBBBBBBBB" //mark the payload clearly
			);
	print_frame(&x);

	return 0;
}

/*
 * output from git aa28914f1813be97878df0fecf1c0a1d59964187
0x41 == nonce
0x42 == payload
           destination         source       type (16 bits)
        _________________ _________________ _____
0x0000  00 00 00 c4 cc 5e 00 00 01 61 ae 1f 00 05 41 41
0x0010  41 41 41 41 41 41 41 41 41 41 41 41 41 41 00 0d <- frame number, uin16
0x0020  42 42 42 42 42 42 42 42 42 42 42 42 42 42 42 42
0x0030  ff ff <- CRC16
*/
