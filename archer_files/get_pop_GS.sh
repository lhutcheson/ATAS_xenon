for int in {1.1,1.3,1.5,1.7,1.9,2.2,2.5} ; 
	do (
	tail -n 1 int$int/delay_+_5.75/data/pop_GS.Xe_ATAS00000200 >> ./pop_GS.txt ; 
       	sed -i "s/0.29998100000000E+004  /$int,/" ./pop_GS.txt ;
       	
	)

	done

