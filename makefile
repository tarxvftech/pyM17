m17.bin: m17.c
	gcc $^ -o $@
	./$@

clean:
	rm m17.bin
