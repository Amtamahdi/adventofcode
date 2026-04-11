'''
/////////////////////////////////////////
             Part I
/////////////////////////////////////////
'''
Data = open('data.txt','r').read().split('\n') #Stocker la liste des ID dans un tableau

Double = 0 #Variable où on stocke le nombre de doublons par ID
Triple = 0 #Variable où on stocke le nombre de triplets par ID

for Box_ID in Data: #Parcours de chaque ligne du tableau
    for letter in ''.join(set(Box_ID)):  #Parcours de chaque lettre unique de l'ID
        if(Box_ID.count(letter)==2): #Une fois qu'un doublon est détecté, nous sortons de la boucle
            Double +=1;
            break;
    
    for letter in ''.join(set(Box_ID)):
        if(Box_ID.count(letter)==3): #Une fois qu'un triplet est détecté, nous sortons de la boucle.
            Triple +=1;
            break;
print("/////////////////////////////////////////\n          Part I\n/////////////////////////////////////////")
print("Double : ",Double)
print("Triple : ",Triple)
print("Checksum =",Double,"*",Triple,"=",Triple*Double)


'''
/////////////////////////////////////////
             Part II
/////////////////////////////////////////
'''

Common_Id_Box='' 
Common=""
len_Common_Id_Box = 0

for compar in Data: #Choisir un Id box et le comparé aux autres
    if(compar !=''):
        for Id_Box in Data : #Parcourir tout les Id box
            for i in range(len(Id_Box)):
                if compar[i]==Id_Box[i] : #Stocker les caractères commun dans notre 'Commun'
                    Common+=compar[i]; 
                    
            if(len(Common) >= len_Common_Id_Box and len(Common)<len(Id_Box)): #Taille du "Common" doit être grand pour plus de précision, mais pas de taille maximale pour éviter les répétitions
                len_Common_Id_Box = len(Common)
                Common_Id_Box = Common
                
            Common =""   
            
print("/////////////////////////////////////////\n          Part II\n/////////////////////////////////////////")
print("taille des caractères communs: ",len_Common_Id_Box)
print("Id Box commun : ",Common_Id_Box)