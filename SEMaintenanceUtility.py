"""
SEMU - Space Engineers Maintenance Utility
Cleaning up world files for dedicated servers

v2.0 - 24/01/2015
Complete rewrite


TODO: Faction and Player Cleanup (including unused NPC Player cleanup)
"""

import logging as l #For logging, duh
import configparser #For config reading and writing
import xml.etree.ElementTree as ET #Used to read the SE save files
import argparse #Used for CLI arguments
import os #For file system checks & snapshot file working
import shutil #For copying files to backups
import datetime #For timestamps
import sys #for propper sys.exit()
import re #Regex, for determining generic names
import math #for distance calculations
import glob #for asteroid backups

###########################
# Argument parser
###########################
def ConstructArgParser():
    argparser = argparse.ArgumentParser(description="Utility for performing maintenance & cleanup on SE save files.")

    argparser.add_argument('--save-path', '-s', help='Path to the save folder.', required=True) #? used to compress into single item (not list) and will accept it if it's missing
    argparser.add_argument('--skip-backup', '-B', help='Skip backup up the save files.', default=False, action='store_true')
    argparser.add_argument('--big-backup', '-b', help='Save the backups as their own files with timestamps. Can make save folder huge after a few backups.', default=False, action='store_true')
    argparser.add_argument('--object-backup', '-x', help="When removing a world object (that has some useful blocks or loaded cargo), save a backup as an XML file named after the ship", default=False, action='store_true')
    argparser.add_argument('--log-level', '-l', help="Logging level, recommend INFO to see what's been done", 
                           #default="INFO",
                           default="INFO",
                           choices=["INFO", "DEBUG", "WARNING", "ERROR", "CRITICAL"])
    argparser.add_argument('--cleanup-objects', '-c', help="Cleanup player-build objects that don't match action. POWERED removes any object that doesn't have a fueled / charged power source. BLOCK removes any object that doesn't have a block set in the SEMU configuration (e.g. beacon). PB is a mixture of both: must be powered AND have one of those blocks",
                           default="", choices=['powered', 'block', 'pb'], nargs=1)
    argparser.add_argument('--clean-refinery-queue', '-q', help="As of SE 01.043, the refinery queue self-replicates and can easily get out of control and cause serious lag. This removes the 'queue' node from refineries which doesn't seem to really do anything.", default=False, action='store_true')
    argparser.add_argument('--disable-lights', '-L', help="Turns off all spotlights and interior lights.", 
                           default="", choices=["interior", "spot", "both"])
    argparser.add_argument('--cleanup-items', '-i', help="Clean up free floating objects like ores and components.", default=False, action='store_true')
    argparser.add_argument('--cleanup-meteors', '-M', help="Turns out that sometimes, meteors can get included in save files but lose their movement, and sit in space like mines. This will remove them", default=False, action='store_true')
    #Looks like SE does players and factions itself now. Sawheet!
    #argparser.add_argument('--prune-players', '-p', help="Removes old entries in the player list. Considered old if they don't own any blocks and either don't belong to a faction or IsDead is true. WARNING: Running this on a single-player save will force you to respawn.", default=False, action='store_true')
    #argparser.add_argument('--prune-factions', '-f', help="Remove empty factions. Best used with --prune-players to remove dead players", default=False, action='store_true')
    argparser.add_argument('--whatif', '-w', help="For debugging, won't do any backups and won't save changes.", default=False, action='store_true')
    argparser.add_argument('--disable-factories', '-d', help='To save on wasted CPU cycles, turn off idle factories (refineries, assemblers, etc)',default=False, action='store_true')
    argparser.add_argument('--disable-factories-all', '-D', help="Disables factories, regardless if they're idle or not",default=False, action='store_true')
    argparser.add_argument('--disable-timer-blocks', '-T', help="Disables timer blocks",default=False, action='store_true')
    argparser.add_argument('--disable-programmable-blocks', '-P', help="Disables programmable blocks",default=False, action='store_true')
    argparser.add_argument('--stop-movement', '-m', help="Stops all CubeGrid velocity and rotatil, stopping them still to save of physics calculations. WARNING: This will affect NPC ships as well, may lead to a buildup of civilian ships as they rely on inertia to leave the sector.", default=False, action='store_true')
    argparser.add_argument('--remove-stored-tools', '-t', help="Removes player tools from cargo containers. They aren't worth much materials and clutter up save files", default=False, action='store_true')
    argparser.add_argument('--junk-cleanup', '-j', help="Removes extra code that isn't needed including pipe data and cockpit colour picker data. Only good until SE saves again, then the code returns but useful after a server restart and everyone is reconnecting.", default=False, action='store_true')
    argparser.add_argument('--remove-npc-ships', '-n', help='Will remove NPC ships and stations that no one has claimed any part of.', default=False, action='store_true')
    #argparser.add_argument('--ignore-joint', '-I', help="At current, the utility won't remove anything with a joint on it (e.g. motor). This restriction can be ignored but use with caution as it may leave 1-ended joints.", default=False, action='store_true')
        #May be fixed
    #argparser.add_argument('--full-cleanup', '-F', help="A complete cleanup. Cleans Factions, Players, Items and all unpowered Objects. Also soft-disables factories and stops movement", default=False, action='store_true')
        #Made easy with the GUI to create a config
    #argparser.add_argument('--save-asteroids', '-s', help="Saves a copy of all asteroids as they are", default=False, action='store_true')
        #No backing up of asteroids required
    argparser.add_argument("--save-asteroids", "-R", help="Saves a copy of the asteroids for use with asteroid respawning. Good for servers that have custom asteroids.", default = False, action='store_true')
    argparser.add_argument('--respawn-asteroids', '-r', help="If there's nothing close to the asteroids, either revert to backup copy or just remove if backup doesn't exist. WARNING: Only use in infinite world! Otherwise, asteroids will just be removed and not respawned!", default=False, action='store_true')

    #argparser.add_argument('--cleanup-unpowered', '-u', help="When setting up a cleanup, removes objects without reactors or batteries or with unfueled reactors or dead batteries. By default, doesn't count solar panels as power", default=False, action='store_true')
    #argparser.add_argument('--cleanup-include-solar', '-S', help="Normally solar panels are excluded because its impossible to confirm with certainty that it's powered. Using this switch forces them to be included in the power check."
	#    , default=False, action='store_true')
    #argparser.add_argument('--cleanup-missing-attrib', '-c', help="Removes objects that are missing cubes with the given attribute, except those that have cubes that match --cleanup-missing-subtype. A list of attributes can be found on the wiki.", nargs="*", default=[])
    #argparser.add_argument('--cleanup-missing-subtype', '-C', help="Removes objects that are missing cubes with the given subtype, except those that have cubes that match --cleanup-missing-attrib. A list of subtypes can be found on the wiki.", nargs="*", default=[])
        #Obsolete under rewrite
    
    
    return argparser


#######################################
# Start logging
#######################################
def StartLogging(logLevelString):
    logFolder = "logs"
    if (os.path.exists(logFolder) == False) or os.path.isdir(logFolder) == False:
        os.makedirs(logFolder)

    logformat = "%(asctime)s %(levelname)s: %(message)s"
    logformatdate = "%Y/%m/%d %H:%M:%S"
    fname = "log-%s.txt" % datetime.datetime.now().strftime("%Y-%m-%d # %H-%M-%S")
    l.basicConfig(filename= logFolder+"/"+fname, level= getattr(l, logLevelString.upper()),
                 filemode='w', format=logformat, datefmt=logformatdate)
    consoleLogger = l.StreamHandler()
    consoleLogger.setFormatter(l.Formatter(logformat, logformatdate))
    l.getLogger().addHandler(consoleLogger)

    l.info("Logging initialized")
    
#######################################
# Load config
#######################################
def LoadConfig():
    l.info("Loading config")

    #Default configuration
    config = configparser.SafeConfigParser({
        "asteroid_remove_range" : "2000",
        "type_asteroid" : "MyObjectBuilder_VoxelMap",
        "asteroid_file_suffix" : "vx2", 
        "blocks_not_worth_saving" : "MyObjectBuilder_CubeBlock;MyObjectBuilder_InteriorLight;MyObjectBuilder_ConveyorConnector",
        #Types of blocks that should be ignored when determining wether to backup a removed cubegrid or not
        #Dealing in types, covers both small and large blocks
        "type_cubegrid" : "MyObjectBuilder_CubeGrid",
        "type_floating_object" : "MyObjectBuilder_FloatingObject",
        "type_reactor" : "MyObjectBuilder_Reactor", #Good for both small and large reactors
        "type_battery" : "MyObjectBuilder_BatteryBlock",
        "type_solar" : "MyObjectBuilder_SolarPanel",
        "type_cargo" : "MyObjectBuilder_CargoContainer",
        "type_colorhsvmask" : "MyObjectBuilder_Cockpit;MyObjectBuilder_TimerBlock;MyObjectBuilder_SensorBlock;MyObjectBuilder_ButtonPanel", #Used when cleaning out the ColorHSVMask data, junk data
        "type_factories" : "MyObjectBuilder_Refinery;MyObjectBuilder_Assembler", #Refinery should be good for both normal and blast furnace
        "type_refinery" : "MyObjectBuilder_Refinery", #Used for the Refinery Cleanup function
        "type_assembler" : "MyObjectBuilder_Assembler",
        "type_light_spot" : "MyObjectBuilder_ReflectorLight", #Used for turning off spotlights
        "type_light_interior" : "MyObjectBuilder_InteriorLight", #Used for turning off interior lights
        "type_player_item" : "MyObjectBuilder_PhysicalGunObject", #Player items like welders and guns. Used for removing from cargo containers
        "type_player_item_names" : "AngleGrinderItem;HandDrillItem;WelderItem", #Names of player items to remove. So that tools that need to be manufactured aren't removed
        "type_cleanup_blocks" : "MyObjectBuilder_RadioAntenna;MyObjectBuilder_Beacon;MyObjectBuilder_Reactor", #Used when cleaning up objects that are missing these blocks
        "type_custom_names" : "MyObjectBuilder_RadioAntenna;MyObjectBuilder_LaserAntenna;MyObjectBuilder_Beacon", #Blocks who's custom names are used in calculating ship names, like beacons and antenna
        "type_programmable_block" : "MyObjectBuilder_MyProgrammableBlock",
        "type_timer_block" : "MyObjectBuilder_TimerBlock",
        "type_meteor" : "MyObjectBuilder_Meteor",
        "block_names_to_ignore" : "Antenna;Laser Antenna;Beacon",
        "small_save_filename" : "Sandbox.sbc",
        "large_save_filename" : "SANDBOX_0_0_0_.sbs",
        "cubegrid_backup_folder" : "Cubegrid Backups",
        "voxel_backup_folder" : "voxel backups",
        "npc_names" : "Private Sail;Business Shipment;Commercial Freighter;Mining Carriage;Mining Transport;Mining Hauler;Military Escort;Military Minelayer;Military Transporter" #Names (beacon only) of NPC ships, semicolon (;) separated
    })

    fname = "config.ini"

    #DEBUG
    #if os.path.exists(fname): os.remove(fname)

    if (os.path.isfile(fname)):
        #Exists and is a file
        l.info("Existing config found, reading config")
        config.read(fname)
    else:
        #Doesn't exist, create default
        l.info("No existing log found, creating default")
        cfile = open(fname, 'w')
        config.write(cfile)
        cfile.close()

    #Debug logging
    for key in config.defaults():
        #l.debug(key)
        l.debug("%s: %s"%(key, config.get(config.default_section, key)))

    return config


#######################################
# Load the save files
#######################################
def LoadSaveFiles(smallsavepath, largesavepath, nobackup, bigbackup):
    l.info("Loading save files")
    l.debug("Small save: " + smallsavepath)
    l.debug("Large save: " + largesavepath)
    l.debug("No backup: " + str(nobackup))
    l.debug("Big backup: " + str(bigbackup))

    if (os.path.isfile(smallsavepath) == False):
        l.error("Unable to load small save file\n" + smallsavepath)
        sys.exit()

    if (os.path.isfile(largesavepath) == False):
        l.error("Unable to load large save file\n" + smallsavepath)
        sys.exit()

    if (nobackup == False):
        l.info("Saving backups")
        smallbackupname = smallsavepath + ".backup"
        largebackupname = largesavepath + ".backup"

        

        #If bigbackups, backup for each run
        if (bigbackup == True):
            timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
            smallbackupname = "%s.%s.backup"%(smallsavepath, timestamp)
            largebackupname = "%s.%s.backup"%(largesavepath, timestamp)

        if args.whatif == False:
            l.debug("Writing small save backup")
            shutil.copyfile(smallsavepath, smallbackupname)
            l.debug("Writing big save backup")
            shutil.copyfile(largesavepath, largebackupname)
    #End backup
    
    l.debug("Loading small save")
    xmlsmallsavetree = ET.parse(smallsavepath)
    xmlsmallsave = xmlsmallsavetree.getroot()
    l.debug("Loading big save")
    xmllargesavetree = ET.parse(largesavepath)
    xmllargesave = xmllargesavetree.getroot()

    return xmlsmallsavetree, xmlsmallsave, xmllargesavetree, xmllargesave
    
#######################################
# Simple function to try and find the first Attribute of the XML node
# In SE, is usually a node's type
#######################################
def FindAttrib(objnode):

    if len(objnode.attrib.values()) > 0:
        return list(objnode.attrib.values())[0]
    else:
        return ""


######################################
# Function to quickly get a config value
######################################
def cget(config, varid):
    if config.has_option(None, varid) == False:
        l.error("Unable to find property '%s' in config! This can sometimes be caused by an older config file."%varid)
        l.error("\tDelete the config.ini file in the SEMU directory and try again.")
        raise Exception("Unable to find config property: " + varid)
    else:
        return config.get(config.default_section, varid)

######################################
#Function to get the name of a floating object
######################################
def GetFloatingItemName(objnode):
	#try:
		return "%s : %s"%(FindAttrib(objnode.find('Item').find('PhysicalContent')).replace("MyObjectBuilder_", ""), objnode.find('Item').find('PhysicalContent').find('SubtypeName').text) #type : name e.g. Ore : Iron
	#except: #Just in case it fucks up
		return ""

######################################
# Function to get clust of objects, 
#   if they're joined by pistons, rotors, etc
######################################
#def GetObjectCluster(objectnode, sectorobjects):
#    i = 0
#    clustervar = [objectnode]

#    #Keep adding to the clustervar
#    while i < len(clustervar):
#        for object in clustervar:
#            for block in list(object.find("CubeBlocks")):
#                result = GetOtherJoinEnd(block, sectorobjects)
#                if result != None:
#                    if result not in clustervar:    #Only add if the clustervar doesn't contain it already
#                        clustervar.append(result)   #Tricky multi joins!
#        i = i + 1 #Next in cluster
#    #End clustervar loop

#    return clustervar

######################################
# Function to get clust of objects, 
#   if they're joined by pistons, rotors, etc
# Updated to use the indexed sector objects dictionary
######################################
def GetObjectCluster(objectnode, joins):
    i = 0
    clustervar = [objectnode]

    #Keep adding to the clustervar
    #while i < len(clustervar):
    #    for object in clustervar:
    #        for block in list(object.find("CubeBlocks")):
    #            result = GetOtherJoinEnd(block, sectorobjectsindexed)
    #            if result != None:
    #                if result not in clustervar:    #Only add if the clustervar doesn't contain it already
    #                    clustervar.append(result)   #Tricky multi joins!
    #    i = i + 1 #Next in cluster
    #End clustervar loop

    toProcess = [objectnode]
    haveSeen = [objectnode.find("EntityId").text]
    while i < len(clustervar):
        object = clustervar[i]
        entityId = object.find("EntityId").text
        for j in joins:
            if j.EntityAId == entityId and j.EntityBNode not in clustervar:
                clustervar.append(j.EntityBNode)
            if j.EntityBId == entityId and j.EntityANode not in clustervar:
                clustervar.append(j.EntityANode)
               
        i = i + 1

    return clustervar

#######################################
# Function to find the other half of a join
#######################################
def GetOtherJoinEnd(block, sectorobjects):
    result = None
    attrib = FindAttrib(block)

    if attrib == "MyObjectBuilder_MotorAdvancedStator":
        result = FindSOByBlockValue(block.find("RotorEntityId").text, "EntityId", sectorobjects)

    if attrib == "MyObjectBuilder_MotorAdvancedRotor":
        result = FindSOByBlockValue(block.find("EntityId").text, "RotorEntityId", sectorobjects)

    if attrib == "MyObjectBuilder_ExtendedPistonBase":
        result = FindSOByBlockValue(block.find("TopBlockId").text, "EntityId", sectorobjects)

    if attrib == "MyObjectBuilder_PistonTop":
        result = FindSOByBlockValue(block.find("PistonBlockId").text, "EntityId", sectorobjects)

    if attrib == "MyObjectBuilder_MotorRotor":
        result = FindSOByBlockValue(block.find("EntityId").text, "RotorEntityId", sectorobjects)

    if attrib == "MyObjectBuilder_MotorStator":
        result = FindSOByBlockValue(block.find("RotorEntityId").text, "EntityId", sectorobjects)

    return result

#######################################
# Function to loop through secor objects and find
#   object by entity ID
#######################################
def FindSOByID(idtofind, sectorobjects):

    for object in list(sectorobjects):
        if (FindAttrib(object) == cget(config, "type_cubegrid")):
            if (object.find("ElementId").text == idtofind):
                return object

#######################################
# Function to loop through secor objects and find
#   object by a block's value. Usually an ID of some type
#######################################
#def FindSOByBlockValue(idtofind, blockfieldname, sectorobjects):
#    for object in list(sectorobjects):
#        if (FindAttrib(object) == cget(config, "type_cubegrid")):
#            for block in list(object.find("CubeBlocks")):
#                if (block.find(blockfieldname) != None): #If the block has this field
#                    if (block.find(blockfieldname).text == idtofind):
#                        return object #Return the object, not the block

#####################################
# Function to get the name(s) of the entity cluster
# Custom names are placed at the front
#####################################
def ObjectClusterName(objectcluster):
    #Prep the name object
    nobject = ClusterName()
    namingBlocks = cget(config, "type_custom_names").split(";")
    blockNamesToIgnore = cget(config, "block_names_to_ignore").split(";")
    
    for object in objectcluster:
        nobject.objectNames.append((object.find("EntityId").text , object.find("DisplayName").text)) #Save as tuple
        l.debug("ID: '%s'"%object.find("EntityId").text)
        l.debug("Name: " + object.find("DisplayName").text)

        for block in object.find("CubeBlocks"):
            attrib = FindAttrib(block)
            if attrib in namingBlocks:
                #Is a block that we can use for name finding
                if block.find("CustomName") != None: #Custom name property exists
                    if block.find("CustomName").text != "": #Ignore it if it's blank
                        nobject.AddBlockName(block.find("CustomName").text)
                    

        #End of block loop
    #End of object loop

    #Calculate the primary name
    nobject.CalcPrimaryName()

    return nobject

class ClusterName:
    objectNames = [] #Tuples of (Object ID, Object Name) of the object cluster
    blockNames = [] #List of custom block names like beacon and antenna
    primaryName = "" #If only a single name can be used, use this one. Primarily used with export save names

    def __init__(self):
        self.objectNames = []
        self.blockNames = []
        self.primaryName = ""

    def __str__(self):
        names = []
        for key, value in self.objectNames:
            names.append("'%s' (%s)"%(value, key))
        
        names.extend(self.blockNames)

        return " / ".join(names)

    def AddBlockName(self, blockName):
        if blockName == None:
            return
        if str.strip(blockName) == "":
            return

        l.debug("Testing block name: " + blockName)
        regexString = r"^(%s)(\W(\d)+)*$"%("|".join(cget(config, "block_names_to_ignore").split(";")))
        p = re.compile(regexString, re.IGNORECASE) #Regex used to chekc if it's generic or not
        #e.g. Antenna 1234

        if p.match(blockName) == None and blockName != "":
        #if p.match(blockName) == None:
            self.blockNames.append(blockName)


    def CalcPrimaryName(self):
        if len(self.blockNames) > 0:
            self.primaryName = self.blockNames[0]
        else:
            p = re.compile(r"^(Platform|Large Ship|Small Ship) (\d)+$", re.IGNORECASE) #Regex used to determine if the object name is unique or not
            for k, v in self.objectNames: #Just loop the names, not the ID's
                if p.match(v) == None: #No match, must be custom
                    self.primaryName = v
                    break #Already got one, don't go any further
        #End if

        if self.primaryName == "": #If STILL no primary name
            self.primaryName = self.objectNames[0][1] #Just use the first tuple

        l.debug("Primary name: " + self.primaryName)



        

########################################
# Function that asks the big question: "Should I remove this object cluster?"
#   "Should I remove this object cluster during cleanup?"
#   If should remove, return true
########################################
def ObjectClusterCleanupCheck(objectcluster, cleanmode, requiredblocks = [], removeNpcShip = False, blockNames = [], npcidentities = []):
    hasPower = False
    hasBlock = False
    hasowner = False
    ownernotNPC = False

    for object in objectcluster:
        for block in list(object.find("CubeBlocks")):

            attrib = FindAttrib(block)

            # Required block?
            if attrib in requiredblocks:
                hasBlock = True #Has the required block

            # Power?
            if attrib == cget(config, "type_reactor"):
                #Is block a reactor
                #Must have fuel
                if len(list(block.find("Inventory").find("Items"))) > 0:
                    hasPower = True

            if attrib == cget(config, "type_solar"):
                #Is block a solar panel
                #Don't care, just say yes
                hasPower = True

            if attrib == cget(config, "type_battery"):
                #Is block a battery
                if block.find("CurrentStoredPower").text != "0":
                    #Must have charge
                    hasPower = True

            if block.find("Owner") != None: #Owner node exists
                hasowner = True
                if block.find("Owner").text not in npcidentities:
                    ownernotNPC = True

        #End block loop

    #End cluster loop

    #Check if blockNames contain any NPC names
    hasNpcName = False
    npcBlockNames = cget(config, "npc_names").split(";")
    for bname in blockNames:
        if bname in npcBlockNames:
            hasNpcName = True
            break

    #if removeNpcShip == True and (inertialDampenersOff == True and hasNpcName == True):
    #    l.info("Is an NPC ship (a block has an NPC name and dampners disabled")
    #    return True
    if removeNpcShip == True and (ownernotNPC == False and hasowner == True):
        l.info("Cubegrid soley owned by NPC player, ship is NPC")
        return True
    if cleanmode == "powered":
        l.info("Has power: " + str(hasPower))
        return (hasPower == False) #return true if missing power
    if cleanmode == "block":
        l.info("Has required block: " + str(hasBlock))
        return (hasBlock == False) #Return true if missing required block
    if cleanmode == "pb": #Both
        l.info("Has power: " + str(hasPower))
        l.info("Has required block: " + str(hasBlock))
        return (hasBlock == False or hasPower == False)
        #Return true if missing required block OR missing power
        
#################################
# Function to get the playerID's of
# players that own blocks in this cluster
#################################

def GetClusterOwners(objectcluster, currentownerlist):
    for object in objectcluster:
        for block in object.find("CubeBlocks"):
            if block.find("Owner") != None:
                blockowner = block.find("Owner").text
                if blockowner not in currentownerlist:
                    currentownerlist.append(blockowner)
    
    return currentownerlist

############################################
# Function to stop object cluster movement
############################################
def StopMovement(objectcluster):
    l.info("Stopping movement")
    for object in objectcluster:
        if object.find('LinearVelocity') != None:
            object.find('LinearVelocity').attrib["x"] = "0"
            object.find('LinearVelocity').attrib["z"] = "0"
            object.find('LinearVelocity').attrib["y"] = "0"
        else:
            l.error("Error: Unable to find LinearVelocity node!")

        if object.find('AngularVelocity') != None:
            object.find('AngularVelocity').attrib["x"] = "0"
            object.find('AngularVelocity').attrib["y"] = "0"
            object.find('AngularVelocity').attrib["z"] = "0"
        else:
            l.error("Error: Unable to find AngularVelocity node!")

#############################################
# Function to find the distance to the closest object
# Used to see if everything is far enough away from an asteroid
#   to remove it
#############################################
def ClearanceDistance(centerobject, sectorobjects):
    final = -1.0
    centerpoint = GetPositionXYZ(centerobject)
    for object in list(sectorobjects):
        if FindAttrib(object) != cget(config, "type_asteroid"): #Ignore tests against other asteroids
            xpoint = GetPositionXYZ(object)
            #distance = (tx - (z * z)) + (ty - (y * y)) + (tz - (z * z))
            #distance = distance / distance

            vector = [centerpoint[0] - xpoint[0], centerpoint[1] - xpoint[1], centerpoint[2] - xpoint[2]]

            #Fix for objects a crazy distance away from the centre. Thanks go to deltaflyer4747
            try:
                distance = math.sqrt(math.pow(vector[0], 2) + math.pow(vector[1], 2) + math.pow(vector[2], 2))
            except:
                distance = final

            if distance < final or final == -1.0:
            
                final = distance

    l.info("Closest distance to another object: " + str(final))
    return final

def GetPositionXYZ(object):
    
    if object.find("PositionAndOrientation") != None:
        if object.find("PositionAndOrientation").find("Position") != None:
            info = object.find("PositionAndOrientation").find("Position")
            return float(info.attrib["x"]), float(info.attrib["y"]), float(info.attrib["z"])
        else:
            throw ("Error: Can't find Position node!")
    else:
        l.error("Error: Can't find PositionAndOrientation node!")

##############################################
# Function to check if an asteroid backup exists
##############################################
def VoxelHasBackup(voxelname):
    voxelname = voxelname + "." + cget(config, "asteroid_file_suffix")
    backupdir = args.save_path + cget(config, "voxel_backup_folder")

    if (os.path.exists(backupdir)):
        l.debug("Backup exists for voxel")
        lolwut = os.listdir(backupdir)
        r = (voxelname in os.listdir(backupdir))
        return r #Return True or False
    else:
        l.debug("No backup exists for voxel")
        return False


##############################################
# Restore a backed up asteroid
##############################################
def RestoreVoxel(voxelname):
    voxelname = voxelname + "." + cget(config, "asteroid_file_suffix")
    l.debug("Restoring voxel from backup: " + voxelname)
    backupdir = args.save_path + cget(config, "voxel_backup_folder")

    if os.path.exists(backupdir) == False:
        l.error("Attempted to restore voxel from backup, backup dir doesn't exist!")
        return False

    if os.path.isfile(backupdir + "/" + voxelname):
        #Backup exists
        if args.whatif == True:
            l.info("Whatif enabled, skipped restoring voxel")
        else:
            shutil.copyfile(backupdir + "/" + voxelname, args.save_path + voxelname)
    else:
        l.error("Attempted to restore a voxel from backup, failed to find backup file!")
        return False


##############################################
# Function to backup asteroids
##############################################
def SaveAsteroids(savepath):
    l.info("Saving backups of asteroids")

    bakfolder = savepath + cget(config, "voxel_backup_folder") + "/"

    if (os.path.exists(bakfolder) == False) or os.path.isdir(bakfolder) == False:
        os.makedirs(bakfolder)

    #Get a list of asteroid files
    asteroidFiles = glob.glob(savepath + "*.vx2")

    #Save 'em
    for a in asteroidFiles:
        l.info("Backing up: " + os.path.basename(a))
        shutil.copyfile(a, bakfolder + os.path.basename(a))


#############################################
# Function to remove an asteroid from the save, as well
#   as removing the asteroid voxel file
#############################################
def RemoveAsteroid(object, sectorobjects, savepath, whatif):
    roidname = object.find("StorageName").text
    l.info("Removing asteroid: " + roidname)

    fname = "%s%s.%s"%(savepath, roidname, cget(config, "asteroid_file_suffix"))
    l.debug("Asteroid file: " + fname)

    if whatif == True:
        l.info("WhatIf used, not actually removing asteroid file")
    else:
        if os.path.isfile(fname):
            os.remove(fname)
        else:
            l.warning("Warning: unable to locate asteroid file: " + roidname)

    
    sectorobjects.remove(object)

#############################################
# Function to determine if a cubegrid is worth saving
#   a backup of if removed
# Determined by (or):
#   - A loaded cargo container
#   - Over X amount of blocks that aren't trivial (armor blocks, interior lights, etc)
# Returns True (do save) or False (not worth saving, probably a hunk of floating blocks)
#############################################
def SaveAfterRemove(objectcluster):
    hascargo = False
    usefulblockcount = 0
    uselessblocks = cget(config, "blocks_not_worth_saving").split(";")
    if uselessblocks[0] == "":
        uselessblocks = []; #Empty array

    for object in objectcluster:
        for block in list(object.find("CubeBlocks")):
            attrib = FindAttrib(block)
            if attrib not in uselessblocks:
                #If this is not a useless block
                l.debug("Found useful block: " + attrib)
                usefulblockcount = usefulblockcount + 1
            if attrib == cget(config, "type_cargo"):
                if len(list(block.find("Inventory").find("Items"))) > 0:
                    #If the cargo container has stuff in it
                    l.debug("Found loaded cargo container")
                    hascargo = True

    #End block loop

    return (hascargo == True or usefulblockcount >= 5) #Return bool. Either has cargo, or has 5 or more useful blocks


#############################################
# Function to save backup of removed cubegrid
#############################################
def SaveCubeGrid(objectcluster, clusterPrimaryName, savepath):
    bakfolder = savepath + cget(config, "cubegrid_backup_folder")
    nameMaxLength = 30

    if (os.path.exists(bakfolder) == False) or os.path.isdir(bakfolder) == False:
        os.makedirs(bakfolder)

    mininame = clusterPrimaryName
    if len(mininame) > nameMaxLength:
        mininame = mininame[:nameMaxLength]

    fname = "%s/%s - %s.xml" % (bakfolder, mininame, clusternames[1])
    l.info("Saving cubegrid backup: " + fname)
    f = open(fname, 'wb')

    for objectnode in objectcluster:
        xmlString = ET.tostring(objectnode, "UTF-8", "xml")
        f.write(xmlString)

    f.close()

###########################################
# Function to get a list of NPC player entries
###########################################
def GetNPCIdentities(smallsave):
    l.info("Compiling list of NPC identities")
    npcplayers = []

    #for i in smallsave.find("Identities"):
    #    #if i.find("CharacterEntityId").text == "0":
    #    node = i.find("DisplayName")
    #    if node != None:
    #        if i.find("DisplayName").text == "Neutral NPC":
    #            l.debug("Discovered NPC identity " + i.find("IdentityId").text)
    #            npcplayers.append(i.find("IdentityId").text)

    for i in smallsave.find("NonPlayerIdentities"):
        l.debug("Discovered NPC identity " + i.text)
        npcplayers.append(i.text)


    input("pause")
    return npcplayers
    

###########################################
# Function to disable factories (e.g. refineries, furnaces, assembler, etc)
#   of object clusters
###########################################
#def DisableFactories(objectcluster, disablesoft = False, disableforce = False, cleanrefineryqueue = False):
#    if disablesoft == False and disableforce == False and cleanrefineryqueue == False:
#        return #Nothing to do here...

#    for object in objectcluster:
#        for block in list(object.find("CubeBlocks")):
#            attrib = FindAttrib(block)

#            if attrib == cget(config, "type_refinery") and cleanrefineryqueue == True:
#                queueparent = block.find("Queue")
#                if queueparent != None:
#                    queue = queueparent.find("Item")
#                    for i in list():
#                        queue.remove(i) #Clear the queue.

#            if attrib in cget(config, "type_factories").split(";"):
#                #Is a factory, if there's nothing waiting, disable it
#                if (disablesoft == True and len(list(block.find("InputInventory").find("Items"))) == 0) or disableforce == True:
#                    l.info("Disabling factory: " + block.find("EntityId").text)
#                    block.find("Enabled").text = "false" #Disable it


#############################################
# Function to disable lights, either spot, interior or all
#############################################
#def DisableLights(objectcluster, mode):
#    l.info("Disabling lights")
#    removeinterior = (mode == "interior" or mode == "both") #Save as bool
#    removespot = (mode == "spot" or mode == "both") #Save as bool

#    typeinterior = cget(config, "type_light_interior")
#    typespot = cget(config, "type_light_spot")

#    for object in objectcluster:
#        for block in list(object.find("CubeBlocks")):
#            attrib = FindAttrib(block)
#            if (attrib == typeinterior and removeinterior == True) or (attrib == typespot and removespot == True):
#                if block.find("Enabled") != None:
#                    l.debug("Light disabled")
#                    block.find("Enabled").text = "false"


#################################################
# Function to remove player tools stored in cargo containers
# For reporting, return how many tools were removed
#################################################
#def RemoveStoredPlayerTools(objectcluster):
#    countRemoved = 0
#    toolsToRemove = cget(config, "type_player_item_names").split(";")
#    l.info("Removing player tools from cargo")
#    for object in objectcluster:
#        for block in list(object.find("CubeBlocks")):
#            attrib = FindAttrib(block)
#            if attrib == cget(config, "type_cargo"):
#                inventory = block.find("Inventory").find("Items")
#                for item in list(inventory):
#                    if item.find("PhysicalContent") != None:
#                        if FindAttrib(item.find("PhysicalContent")) == cget(config, "type_player_item"):
#                            toolName = item.find("PhysicalContent").find("SubtypeName").text
#                            if toolName in toolsToRemove:
#                                l.debug("Removed tool: " + toolName)
#                                inventory.remove(item)
#                                countRemoved = countRemoved + 1
#    #End loop

#    return countRemoved

#################################################
# Block loop function
# Combines all of the separate functions which process 
#   CubeGrid blocks into one loop. Saves relooping over and over again
#################################################
def BlockLoop(objectcluster, removelightsmode = "", 
              removeplayertools = False, removerefineryqueue = False,
              disablefactoriessoft = False, disablefactorieshard = False,
              removejunkcode = False,
              disabletimerblocks = False, disableprogrammableblocks = False
              ):

    if (removelightsmode == '' and
        removeplayertools == False and
        removerefineryqueue == False and
        disablefactoriessoft == False and
        disablefactorieshard == False and
        removejunkcode == False
        ):
        return #Nothing to do here, don't bother wasting CPU


    #Initial variables
    countToolsRemoved = 0
    toolsToRemove = cget(config, "type_player_item_names").split(";")

    disablelightsinterior = (removelightsmode == "interior" or removelightsmode == "both") #Save as bool
    disablelightsspot = (removelightsmode == "spot" or removelightsmode == "both") #Save as bool
    typeInteriorLight = cget(config, "type_light_interior")
    typeSpotLight = cget(config, "type_light_spot")

    typeAssembler = cget(config, "type_assembler")
    typeRefinery = cget(config, "type_refinery")

    typeHSVMask = cget(config, "type_colorhsvmask").split(";")

    for object in objectcluster:
        for block in list(object.find("CubeBlocks")):
            attrib = FindAttrib(block)

            #Remove player tools from cargo
            if attrib == cget(config, "type_cargo") and removeplayertools == True:
                inventory = block.find("Inventory").find("Items")
                for item in list(inventory):
                    if item.find("PhysicalContent") != None:
                        if FindAttrib(item.find("PhysicalContent")) == cget(config, "type_player_item"):
                            toolName = item.find("PhysicalContent").find("SubtypeName").text
                            if toolName in toolsToRemove:
                                l.debug("Removed tool: " + toolName)
                                inventory.remove(item)
                                #countRemoved = countRemoved + 1
            #End remove player tools

            #Disable lights
            if (attrib == typeInteriorLight and disablelightsinterior == True) or (attrib == typeSpotLight and disablelightsspot == True):
                if block.find("Enabled") != None:
                    l.debug("Light disabled: " + attrib)
                    block.find("Enabled").text = "false"
            #End lights

            #Disable Refinery
            if attrib == typeRefinery:
                #Is a factory, if there's nothing waiting, disable it
                if (disablefactoriessoft == True and len(list(block.find("InputInventory").find("Items"))) == 0) or disablefactorieshard == True:
                    l.info("Disabling refinery: " + block.find("EntityId").text)
                    block.find("Enabled").text = "false" #Disable it
            #Disable assembler
            if attrib == typeAssembler:
                #Is an assembler. if there's nothing queued or inventory empty, disable it
                if (disablefactoriessoft == True and (len(list(block.find("InputInventory").find("Items"))) == 0)) or disablefactorieshard == True:
                    l.info("Disabling refinery: " + block.find("EntityId").text)
                    block.find("Enabled").text = "false" #Disable it
            #Remove refinery queue
            if attrib == typeRefinery and removerefineryqueue == True:
                l.info("Clearing refinery queue: " + block.find("EntityId").text)
                queueparent = block.find("Queue")
                if queueparent != None:
                    queue = queueparent.find("Item")
                    for i in list():
                        queue.remove(i) #Clear the queue.

            #Remove ColorMaskHSVList from seats, part of junk code cleanup
            if attrib in typeHSVMask:
                if block.find("Toolbar") != None:
                    if block.find("Toolbar").find("ColorMaskHSVList") != None:
                        hsv = block.find("Toolbar").find("ColorMaskHSVList")
                        l.debug("Removing ColorMaskHSVList, junk code")
                        for i in list(hsv):
                            hsv.remove(i)
            #End ColorMaskHSVList if

            #Disable timer blocks
            if attrib == cget(config, "type_timer_block") and disabletimerblocks == True:
                if block.find("Enabled") != None:
                    l.debug("Disabling timer block")
                    block.find("Enabled").text = "false"

            #Disable programmable blocks
            if attrib == cget(config, "type_programmable_block") and disableprogrammableblocks == True:
                if block.find("Enabled") != None:
                    l.debug("Disabling programmable block")
                    block.find("Enabled").text = "false"
            
        #End block loop

        #Remove conveyor lines, part of junk code cleanup
        if removejunkcode == True:
            if object.find("ConveyorLines") != None:
                cl = object.find("ConveyorLines")
                l.debug("Removing ConveyorLines, part of junk code cleanup")
                for i in list(cl):
                    cl.remove(i)


#########################################
# Entity indexing function
# Issues were encountered with large save files and 
#   entities complex entity clusters. 
# Puts entities into an Dictionary array with the 
#   entity ID as the index. Should make mapping entity clusters
#    much faster
#########################################
def IndexSectorObjects(sectorObjects):
    l.info("Indexing Sector objects")
    joinEndsA = [] #A ends are ends that have the reference to another object
    joinEndsB = [] #B ends are ends that don't reference another object. Will be iterated by A ends

    for entity in sectorObjects:
        if entity.find("CubeBlocks") != None:
            entityId = entity.find("EntityId").text
            for block in entity.find("CubeBlocks"):
                if block.find("EntityId") != None:
                    blockId = block.find("EntityId").text
                    attrib = FindAttrib(block)
                    #A Type joins
                    if attrib == "MyObjectBuilder_MotorAdvancedStator" or attrib == "MyObjectBuilder_MotorStator":
                        if block.find("RotorEntityId") != None: #If it's missing
                            if block.find("RotorEntityId").text != "0": #If it's 0, no rotor joined
                                joinEndsA.append(JoinEnd(entity, blockId, entityId, block.find("RotorEntityId").text))
                    
                    if attrib == "MyObjectBuilder_ExtendedPistonBase":
                        joinEndsA.append(JoinEnd(entity, blockId, entityId, block.find("TopBlockId").text))

                    #B type joins, just record them. They'll be matched up later
                    if attrib == "MyObjectBuilder_MotorAdvancedRotor" or attrib == "MyObjectBuilder_PistonTop" or attrib == "MyObjectBuilder_MotorRotor":
                        joinEndsB.append(JoinEnd(entity, blockId, entityId, None))

    #Table assembled, lets match them
    joins = []
    for JoinA in joinEndsA:
        match = None
        for j in joinEndsB:
            if j.BlockId == JoinA.OtherEnd:
                match = j
                break
        #match = next(j for j in joinEndsB if j.EntityId == JoinA.OtherEnd)

        if match != None:
            #Match found
            joins.append(JoinEntry(JoinA.EntityId, JoinA.ParentNode, match.EntityId, match.ParentNode))

    #Return the join table
    return joins
        
class JoinEnd:
    EntityId = "" #EntityId of the parent entity
    BlockId = "" #EntityId of this block
    ParentNode = None #SectorObject node
    OtherEnd = "" #EntityId of the other block (if it's a JoinEndA

    def __init__(self, ParentNode, BlockId, EntityId, OtherEnd):
        self.ParentNode = ParentNode
        self.BlockId = BlockId
        self.EntityId = EntityId
        self.OtherEnd = OtherEnd

class JoinEntry:
    EntityAId = ""
    EntityANode = None
    EntityBId = ""
    EntityBNode = None

    def __init__(self, EntityAId, EntityANode, EntityBId, EntityBNode):
        self.EntityAId = EntityAId
        self.EntityANode = EntityANode
        self.EntityBId = EntityBId
        self.EntityBNode = EntityBNode

def GetOtherJoinEnd(block, sectorobjects):
    result = None
    attrib = FindAttrib(block)

    if attrib == "MyObjectBuilder_MotorAdvancedStator":
        result = FindSOByBlockValue(block.find("RotorEntityId").text, "EntityId", sectorobjects)

    if attrib == "MyObjectBuilder_MotorAdvancedRotor":
        result = FindSOByBlockValue(block.find("EntityId").text, "RotorEntityId", sectorobjects)

    if attrib == "MyObjectBuilder_ExtendedPistonBase":
        result = FindSOByBlockValue(block.find("TopBlockId").text, "EntityId", sectorobjects)

    if attrib == "MyObjectBuilder_PistonTop":
        result = FindSOByBlockValue(block.find("PistonBlockId").text, "EntityId", sectorobjects)

    if attrib == "MyObjectBuilder_MotorRotor":
        result = FindSOByBlockValue(block.find("EntityId").text, "RotorEntityId", sectorobjects)

    if attrib == "MyObjectBuilder_MotorStator":
        result = FindSOByBlockValue(block.find("RotorEntityId").text, "EntityId", sectorobjects)

    return result

#########################################################################
### Main code block                                                 #####
#########################################################################

#ArgParse
argParser = ConstructArgParser() 
args = argParser.parse_args()
#args = argParser.parse_args(["-s", r"C:\Users\Davo\AppData\Roaming\SpaceEngineers\Saves\76561197992643360\TestBed", "--stop-movement", "-l", "DEBUG"])
#args = argParser.parse_args([r"D:\Dump\SE TEST\Solar Dream", "-m", "-i", "-c", "powered", "-x", "-q", "-L", "both", "-d", "-t", "-j"])

#Initiate logging
StartLogging(args.log_level)

#Show some stuff
l.debug("Args:")
for k in args.__dict__:
    if args.__dict__[k] is not None:
        l.debug("%s = %s" % (k, args.__dict__[k]))

#SavePath: Replace all "\" with "/" and add an "/" on the end if it's missing
args.save_path = args.save_path.replace("\\","/")
if args.save_path[-1:] != "/":
	args.save_path = args.save_path + "/"

#Load config
config = LoadConfig()

#If saving asteroids, don't do anything else except save
if (args.save_asteroids == True):
    if args.whatif == True:
        l.info("What-if used, no action taken")
    else:
        SaveAsteroids(args.save_path)
    l.info("Asteroid backup complete, exiting")
    sys.exit()


#Make sure that you've got something to do
if (args.cleanup_objects == '' and
    args.clean_refinery_queue == False and
    args.disable_lights == "" and
    args.cleanup_items == False and
    args.disable_factories == False and
    args.disable_factories_all == False and
    args.stop_movement == False and
    args.remove_stored_tools == False and
    args.respawn_asteroids == False and
    args.remove_npc_ships == False
    ):
    
    #raise Exception("Error: No actions given")
	l.critical("Error: No actions given.")
	sys.exit()

#Load save
xmlsmallsavetree, xmlsmallsave, xmllargesavetree, xmllargesave = LoadSaveFiles(
    args.save_path + config.get(config.default_section, "small_save_filename"),
    args.save_path + config.get(config.default_section, "large_save_filename"),
    args.skip_backup,
    args.big_backup
    )

#Try to find the Sector Objects node
if xmllargesave.find('SectorObjects') == None:
	l.error("Error: Unable to locate SectorObjects node!")
	sys.exit()

sectorobjects = xmllargesave.find('SectorObjects')

joinsTable = IndexSectorObjects(sectorobjects)
#sectorObjectsIndexed = IndexSectorObjects(sectorobjects)

#Init the ownership table
#This is a list of players that own stuff
owningplayers = []

#Get list of NPC identities
npcidentities = GetNPCIdentities(xmlsmallsave)

#For final report
countClustersRemoved = 0
countClustersRemain = 0
countItemsRemoved = 0
countPlayerToolsRemoved = 0
listCubegridsRemoved = []
listVoxelsToRemove = []

l.info("Beginning Sector Object check")

###############################################################################
# Sector Objects Loop
###############################################################################

#Loop through all the elements in the SectorObjects node
#after checking, only i++ if the object wasn't removed
#If object was removed, DO NOT i++, after removing, that index will be rechecked
#   This is to accomodate removing multiple elements in one go and not stuffing up loop indexing
i = 0
havechecked = []
while i < len(sectorobjects):
    object = sectorobjects[i]
    objectclass = FindAttrib(object)
    l.debug("= Next object =")
    l.debug("Object type: " + objectclass)

    #If a floating object
    if objectclass == cget(config, "type_floating_object"):
        if args.cleanup_items == True:
            l.info("===Removing free-floating object: " + object.find("EntityId").text + " " + GetFloatingItemName(object) + "===")
            sectorobjects.remove(object)
            countItemsRemoved = countItemsRemoved + 1
            continue #Next object
        if args.stop_movement == True:
            StopMovement([object])

    #If it's a meteor
    if objectclass == cget(config, "type_meteor"):
        if args.cleanup_meteors == True:
            l.info("===Removing meteor: " + object.find("EntityId").text + " ===")
            sectorobjects.remove(object)

    #If an asteroid
    if objectclass == cget(config, "type_asteroid") and args.respawn_asteroids == True:
        #find the closest object. If it's far enough away, remove the asteroid
        #If there's a backup, restore the backup. Otherwise, just remove the asteroid. In an infinite universe, it'll be respawned
        voxelname = object.find("StorageName").text
        l.info("===Processing asteroid / voxel map: %s / %s==="%(object.find("EntityId").text, voxelname))
        clearance = ClearanceDistance(object, sectorobjects)
        distmin = float(cget(config, "asteroid_remove_range"))
        if clearance > distmin:
            
            if VoxelHasBackup(voxelname): #True if it has a backup saved
                #Has backup, restore from backup
                RestoreVoxel(voxelname)
            else: #No backup, just remove it
                RemoveAsteroid(object, sectorobjects, args.save_path, args.whatif)
        else:
            l.info("Not removing asteroid, something's close to it")

    #If a cubegrid
    if objectclass == cget(config, "type_cubegrid"):
        #If a cubegrid and it's seen it before, ignore it
        if object in havechecked:
            l.debug("Already seen this next cubegrid, moving on")
            i = i + 1
            continue

        #Get the object as a cluster, in case it's joined by rotors, pistons, etc
        objectcluster = GetObjectCluster(object, joinsTable)
        clusterNameObject = ObjectClusterName(objectcluster)
        l.debug("ClusterNameObject: " + clusterNameObject.primaryName) #Checking on issue where it would sometimes be blank
        l.info("===Processing object%s: %s==="%(
            (" cluster" if len(objectcluster) == 1 else ""),
            str(clusterNameObject)
            ))

        if len(args.cleanup_objects) > 0: #If object cleanup needed
            if ObjectClusterCleanupCheck(objectcluster, args.cleanup_objects[0], cget(config, "type_cleanup_blocks").split(";"), args.remove_npc_ships, clusterNameObject.blockNames, npcidentities) == True: #Cleanup o'clock!
                #Make a backup before removing (if needed)
                if args.object_backup == True:
                    if SaveAfterRemove(objectcluster):
                        SaveCubeGrid(objectcluster, clusterNameObject.primaryName, args.save_path)

                l.info("- Removing object(s)")
                countClustersRemoved = countClustersRemoved + 1
                for object in objectcluster:
                   listCubegridsRemoved.append(str(clusterNameObject))
                   sectorobjects.remove(object)
                continue #Next sector object
            else:
                l.info("- NOT removing object(s)")

        #Made it out there, not cleaned up
        #Do other CubeGrid stuff
        BlockLoop(objectcluster, args.disable_lights, 
                  args.remove_stored_tools, args.clean_refinery_queue,
                  args.disable_factories, args.disable_factories_all,
                  args.junk_cleanup,
                  args.disable_timer_blocks, args.disable_programmable_blocks)

        #Add block owners to list of players that own stuff
        #Disabled for now, looks like player pruning is done in SE now. Woo!
        #owningplayers = GetClusterOwners(objectcluster, owningplayers)

        #Turn off factories & clean refineries
       # DisableFactories(objectcluster, args.disable_factories, args.disable_factories_all, args.clean_refinery_queue)

        #Remove player tools in cargo holds
        #if args.remove_stored_tools == True:
        #    countPlayerToolsRemoved = countPlayerToolsRemoved + RemoveStoredPlayerTools(objectcluster)

        #Turn off spotlights
        #if args.disable_lights != "":
        #    DisableLights(objectcluster, args.disable_lights)

        #Stop movement
        if args.stop_movement == True:
            StopMovement(objectcluster)

        #Made it to here, cubegrid must be good
        havechecked.extend(objectcluster)
        countClustersRemain = countClustersRemain + 1
    #End CubeGrid If

    #Processing is complete and object wasn't removed
    i = i + 1

#End Sector Object loop

###
# Player check not included. Looks like SE takes care of Player and Faction entries by itself now
#   Bitchin'!
###

##############################################
# Save the world
##############################################
if args.whatif == False:
    l.info("Saving changes...")

    #For some reason, SpaceEngineers won't dare read the save without this
    xmllargesave.attrib["xmlns:xsd"]="http://www.w3.org/2001/XMLSchema"
    xmlsmallsave.attrib["xmlns:xsd"]="http://www.w3.org/2001/XMLSchema"

    l.debug("Saving large save...")
    xmllargesavetree.write(args.save_path + config.get(config.default_section, "large_save_filename"))

    l.debug("Saving small save...")
    xmlsmallsavetree.write(args.save_path + config.get(config.default_section, "small_save_filename"))
else:
    l.info("===Complete! WhatIf was used, no changes saved===")

#Final report
l.info("Cubegrid clusters removed: " + str(countClustersRemoved))
l.info("Cubegrid clusters remaining: " + str(countClustersRemain))
#if countPlayerToolsRemoved > 0: l.info("Player tools removed from containers: " + str(countPlayerToolsRemoved))
if countItemsRemoved > 0: l.info("Free-floating items removed: " + str(countItemsRemoved))