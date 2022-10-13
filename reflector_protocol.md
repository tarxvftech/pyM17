```
#So the full flow is kinda like follows:
Ether / IP / UDP / 192.168.170.99:52571 > 51.81.119.111:17000 DVRef 'CONN' 'W2FBI   D' > 0x5a
#(0x5a is 'Z', so this means "W2FBI D" is connecting to the reflector's module 'Z'.
#Notice that the connecting callsign's _last_ character is the reflector module - there's more than one space between 'I' and 'D' in "W2FBI   D"
#If the reflector lets us in, we get an ACKN and can send data. If we get a NACK, we're not allowed in for some reason. #Possible reasons include already having an existing session that hasn't timed out yet (common when you're developing). Send the DISC message before a CONN if you suspect this.
﻿
Ether / IP / UDP / 51.81.119.111:17000 > 192.168.170.99:52571 DVRef 'ACKN' / Padding
﻿
#Hurrah! We got in. Send a voice stream (Where it says M17[0x11a8, 0x0] those are the streamid and frame number.
#The source callsign in this stream is wrong - it should match what we CONN'd with. Sorry!
Ether / IP / UDP / DVRef / 192.168.170.99:52571 > 51.81.119.111:17000 M17[0x11a8, 0x0] 'W2FBI   Z' > 'M17-M17 Z'  / C2_3200
Ether / IP / UDP / DVRef / 192.168.170.99:52571 > 51.81.119.111:17000 M17[0x11a8, 0x1] 'W2FBI   Z' > 'M17-M17 Z'  / C2_3200
Ether / IP / UDP / DVRef / 192.168.170.99:52571 > 51.81.119.111:17000 M17[0x11a8, 0x2] 'W2FBI   Z' > 'M17-M17 Z'  / C2_3200
Ether / IP / UDP / DVRef / 192.168.170.99:52571 > 51.81.119.111:17000 M17[0x11a8, 0x3] 'W2FBI   Z' > 'M17-M17 Z'  / C2_3200
Ether / IP / UDP / DVRef / 192.168.170.99:52571 > 51.81.119.111:17000 M17[0x11a8, 0x4] 'W2FBI   Z' > 'M17-M17 Z'  / C2_3200
Ether / IP / UDP / DVRef / 192.168.170.99:52571 > 51.81.119.111:17000 M17[0x11a8, 0x5] 'W2FBI   Z' > 'M17-M17 Z'  / C2_3200
Ether / IP / UDP / DVRef / 192.168.170.99:52571 > 51.81.119.111:17000 M17[0x11a8, 0x6] 'W2FBI   Z' > 'M17-M17 Z'  / C2_3200
Ether / IP / UDP / DVRef / 192.168.170.99:52571 > 51.81.119.111:17000 M17[0x11a8, 0x7] 'W2FBI   Z' > 'M17-M17 Z'  / C2_3200
Ether / IP / UDP / DVRef / 192.168.170.99:52571 > 51.81.119.111:17000 M17[0x11a8, 0x8] 'W2FBI   Z' > 'M17-M17 Z'  / C2_3200
Ether / IP / UDP / DVRef / 192.168.170.99:52571 > 51.81.119.111:17000 M17[0x11a8, 0x9] 'W2FBI   Z' > 'M17-M17 Z'  / C2_3200
Ether / IP / UDP / DVRef / 192.168.170.99:52571 > 51.81.119.111:17000 M17[0x11a8, 0xa] 'W2FBI   Z' > 'M17-M17 Z'  / C2_3200
Ether / IP / UDP / DVRef / 192.168.170.99:52571 > 51.81.119.111:17000 M17[0x11a8, 0xb] 'W2FBI   Z' > 'M17-M17 Z'  / C2_3200
Ether / IP / UDP / DVRef / 192.168.170.99:52571 > 51.81.119.111:17000 M17[0x11a8, 0xc] 'W2FBI   Z' > 'M17-M17 Z'  / C2_3200
Ether / IP / UDP / DVRef / 192.168.170.99:52571 > 51.81.119.111:17000 M17[0x11a8, 0xd] 'W2FBI   Z' > 'M17-M17 Z'  / C2_3200
Ether / IP / UDP / DVRef / 192.168.170.99:52571 > 51.81.119.111:17000 M17[0x11a8, 0x800e] 'W2FBI   Z' > 'M17-M17 Z'  / C2_3200
# Notice the frame number has the high bit set, indicating the last frame.
﻿
Ether / IP / UDP / DVRef / 51.81.119.111:17000 > 192.168.170.99:52571 M17[0x11a8, 0x800e] 'W2FBI   Z' > 'W2FBI   D'  / C2_3200
#The reflector sent our own EOT packet back to us for some reason. Oh well.
Ether / IP / UDP / 51.81.119.111:17000 > 192.168.170.99:52571 DVRef 'PING' 'M17-M17' / Padding
#Server sends a PING every 3s or so, usually. Could be longer.
Ether / IP / UDP / 192.168.170.99:52571 > 51.81.119.111:17000 DVRef 'PONG' 'W2FBI   D'
#We PONG back since we got a PING.
﻿
#Alright, we're done, send a DISC.
Ether / IP / UDP / 192.168.170.99:52571 > 51.81.119.111:17000 DVRef 'DISC' 'W2FBI   D'
#Reflector responds with a DISC to confirm.
Ether / IP / UDP / 51.81.119.111:17000 > 192.168.170.99:52571 DVRef 'DISC' '' / Padding
```
