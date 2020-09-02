m17_frame_explainer: m17.c
	gcc $^ -o $@
	./$@

clean:
	rm m17_frame_explainer
