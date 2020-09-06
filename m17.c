#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <arpa/inet.h>

int indexOf(const char * haystack, char needle);

const char * m17_callsign_alphabet = " ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-/.";
//                                    0123456789ABCDEF...
 
uint64_t m17_callsign2addr( const char * callsign ){
	uint64_t encoded = 0;
	int clen = strlen(callsign)-1; //skip the null byte
	for( int i = clen; i >= 0; i-- ){
		//yes, this is slower even than the reference implementation - but it's easier to modify, a good thing for our test bed.
		//(and it's not noticeably slower in the practical sense for a full PC)
		int charidx = indexOf(m17_callsign_alphabet,callsign[i]);
		if( charidx == -1 ){
			//replace invalid characters with spaces
			charidx = 0;
		}
		encoded *= 40;
		encoded += charidx;
		if( encoded >= 262144000000000 ){ //40**9
			//invalid callsign
			return -1;
		}
	}
	return encoded;
}
int indexOf(const char * haystack, char needle){
	char * sp = strchr( haystack, needle);
	if( sp == NULL ){ 
		return -1; 
	} 
	return (int)(sp-haystack);
}
uint64_t encode_callsign_base40(const char *callsign) {
	//straight from the spec, unedited and unchecked
	uint64_t encoded = 0;
	for (const char *p = (callsign + strlen(callsign) - 1); p >= callsign; p-- ) {
		encoded *= 40;

		// If speed is more important than code space, you can replace this with a lookup into a 256 byte array.
		if (*p >= 'A' && *p <= 'Z'){  // 1-26
			encoded += *p - 'A' + 1;
		} else if (*p >= '0' && *p <= '9'){  // 27-36
			encoded += *p - '0' + 27;
		} else if (*p == '-'){  // 37
			encoded += 37;
		} else if (*p == '/'){  // 38
			encoded += 38;
		// This . is just a place holder. Change it if it makes more sense, 
		// Be sure to change them in the decoder too.
		} else if (*p == '.'){  // 39
			encoded += 39;
		} else{
			// Invalid character or a ' ', represented by 0. (which gets decoded to ' ')
			;
		}
	}
	return encoded;
}
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
	char     magic[4];
	uint16_t streamid;		
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
		uint16_t streamid,
		uint64_t dst,
		uint64_t src,
		uint16_t frametype,
		char *   nonce,
		uint16_t framenumber,
		uint8_t* payload
		){
	uint8_t *y = (uint8_t *) x;
	memset(y, 0, sizeof(M17_IPFrame));
	strncpy(x->magic, "M17 ", 4); //magic bytes to support easy multiplexing with other protocols
	x->streamid = htons(0xCCCC);
	init_lich(&x->lich, dst,src,frametype,nonce);
	x->framenumber = htons(framenumber);
	memcpy(x->payload, payload, 16);
	x->crc[0] = 0xff;
	x->crc[1] = 0xff;
}
void explain_frame(){
	M17_IPFrame x;
	init_frame(&x, 
			0xCCCC, //streamid
			encode_callsign_base40("XLX307 D"),
			encode_callsign_base40("W2FBI"),
			5, //voice stream
			"AAAAAAAAAAAAAAAA", //mark out the nonce clearly
			13, //just as an example
			"BBBBBBBBBBBBBBBB" //mark the payload clearly
			);
	uint8_t *y = (uint8_t *) &x;
	printf("0x41 == nonce\n");
	printf("0x42 == payload\n");
	printf("0xCC == streamid\n");
	printf("fn is the frame number, where the high bit (leftmost) indicates last packet in the stream\n");
	printf("\n");
	printf("           \"M17 \"    SID     destination      source (continued next line)\n");
	printf("        ___________ _____ _________________ ___________\n");
	char * indent = "        ";
	for( int i = 0; i < sizeof(M17_IPFrame); i++){
		if( i == 16 ){
			printf("\n\n%s_src_",indent);
			printf(" type_ _____0x41 == nonce_________________   ");
		}
		if( i == 32 ){
			printf("\n\n%s__nonce____ _fn__ ______payload________________",indent);
			printf("  fn is the frame number");
		}
		if( i == 0x30 ){
			printf("\n\n%s__more payload___ CRC16",indent);
		}
		if( i>0 && i %16 == 0){ printf("\n"); }
		if(i%16==0){ printf("0x%04x  ",i); }
		printf("%02x ", y[i]);
		/*if( i == 49 ) printf("<- CRC16");*/
	}
}

typedef uint64_t (*callsign_func)(const char *callsign);
int callsign_test(const char * callsign, uint64_t expected ){
#define fns_len 2
	callsign_func fns[fns_len] = {
		m17_callsign2addr,
		encode_callsign_base40
	};
	char * fn_names[fns_len] = {
		"m17_callsign2addr",
		"encode_callsign_base40"
	};
	uint64_t results[fns_len];

	for( int i = 0; i < fns_len; i++){
		results[i] = (*fns[i])(callsign);
	}

	printf("Results: \n");
	int all_ok = 1;
	for( int i = 0; i < fns_len; i++){
		int ok = results[i] == expected;
		printf("\t%s\t0x%08lx\t%s\n", ok?"✔":"╳", results[i], fn_names[i] );
		if( !ok ){
			printf("\t\t0x%08lx expected\n", expected);
			all_ok = 0;
		}
	}
	return all_ok;
}
void callsign_tests(){
	int errors = 0;
	errors += !callsign_test("M17", 55533);
	errors += !callsign_test("W2FBI", 0x0161ae1f);
	errors += !callsign_test("XLX307 D", 0x00996A4193F8);
	printf("%d errors\n", errors);
}
int main(int argc, char **argv){
	callsign_tests();
	explain_frame();

	return 0;
}

/*
 * output from git aa28914f1813be97878df0fecf1c0a1d59964187
0x41 == nonce
0x42 == payload
0xCC == streamid
fn is the frame number, where the high bit (leftmost) indicates last packet in the stream

           "M17 "    SID     destination      source (continued next line)
        ___________ _____ _________________ ___________
0x0000  4d 31 37 20 cc cc 00 99 6a 41 93 f8 00 00 01 61

        _src_ type_ _____0x41 == nonce_________________
0x0010  ae 1f 00 05 41 41 41 41 41 41 41 41 41 41 41 41

        __nonce____ _fn__ ______payload________________  fn is the frame number
0x0020  41 41 41 41 00 0d 42 42 42 42 42 42 42 42 42 42

        __more payload___ CRC16
0x0030  42 42 42 42 42 42 ff ff

*/
