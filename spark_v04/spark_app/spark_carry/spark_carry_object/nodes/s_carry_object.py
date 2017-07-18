#!/usr/bin/env python
# -*- coding: utf-8 -*-

import cv2
import os
import time 
import random
import ctypes
import roslib
import rospy
import smach
import smach_ros
import threading
import thread
import string
import math
import cv2
import numpy as np
from geometry_msgs.msg import Twist
from std_msgs.msg import String
from spark_carry_object.srv import *
from swiftpro.msg import *
from cv_bridge import CvBridge, CvBridgeError
from sensor_msgs.msg import Image

from tf import TransformListener
import tf

import actionlib
from actionlib import GoalStatus
from move_base_msgs.msg import MoveBaseAction, MoveBaseGoal, MoveBaseActionFeedback

from smach import State, StateMachine, Concurrence, Container, UserData
from smach_ros import MonitorState, ServiceState, SimpleActionState, IntrospectionServer
from geometry_msgs.msg import Pose, Point, Quaternion

move_base = actionlib.SimpleActionClient("move_base", MoveBaseAction)

class GraspObject(State):
    '''
    抓取物体 功能
    '''
    def __init__(self):
        '''
        初始化
        '''
		global sub, pub1, pub2
		global xc, yc, xc_prev, yc_prev, found_count
        State.__init__(self, outcomes=['succeeded', 'aborted'])
        self.task = 'grasp object'
		xc = 0
		yc = 0
		xc_prev = xc
		yc_prev = yc
		found_count = 0
		rospy.init_node('image_converter', anonymous=True)
		sub  = rospy.Subscriber("/camera/rgb/image_raw", Image, self.image_callback)
		pub1 = rospy.Publisher('position_write_topic', position, queue_size=10)
		pub2 = rospy.Publisher('pump_topic', status, queue_size=1)
		
		try:
			rospy.spin()
		except KeyboardInterrupt:
			print("Shutting down")
		cv2.destroyAllWindows()

	def image_callback(self, data):
		global xc, yc, xc_prev, yc_prev, found_count
		# change to opencv
		try:
			cv_image1 = CvBridge().imgmsg_to_cv2(data, "bgr8")
		except CvBridgeError as e:
			print('error')
	
		# change rgb to hsv
		cv_image2 = cv2.cvtColor(cv_image1, cv2.COLOR_BGR2HSV)
	
		# extract blue
		LowerBlue = np.array([100, 90, 80])
		UpperBlue = np.array([130, 255, 255])
		mask = cv2.inRange(cv_image2, LowerBlue, UpperBlue)
		cv_image3 = cv2.bitwise_and(cv_image2, cv_image2, mask=mask)
	
		# gray process
		cv_image4 = cv_image3[:,:,0]
	
		# smooth and clean noise
		blurred = cv2.blur(cv_image4, (9, 9))
		(_, thresh) = cv2.threshold(blurred, 90, 255, cv2.THRESH_BINARY)
		kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (25, 25))
		cv_image5 = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
		cv_image5 = cv2.erode(cv_image5, None, iterations=4)
		cv_image5 = cv2.dilate(cv_image5, None, iterations=4)
	
		# detect contour
		cv2.imshow("win1", cv_image1)
		cv2.imshow("win2", cv_image5)
		cv2.waitKey(1)
		contours, hier = cv2.findContours(cv_image5, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

		# if find contours, pick the biggest box
		if len(contours) > 0:
			size = []
			size_max = 0
			for i, c in enumerate(contours):
				rect = cv2.minAreaRect(c)
				box = cv2.cv.BoxPoints(rect)
				box = np.int0(box)
				x_mid = (box[0][0] + box[2][0] + box[1][0] + box[3][0]) / 4
				y_mid = (box[0][1] + box[2][1] + box[1][1] + box[3][1]) / 4
				w = math.sqrt((box[0][0] - box[1][0])**2 + (box[0][1] - box[1][1])**2)
				h = math.sqrt((box[0][0] - box[3][0])**2 + (box[0][1] - box[3][1])**2) 
				size.append(w * h)
				if size[i] > size_max:
					size_max = size[i]
					index = i
					xc = x_mid
					yc = y_mid
			# if box is not moving for 20 times
			if found_count >= 20:
				self.grasp()
			else:
				# if box is not moving
				if abs(xc - xc_prev) <= 2 and abs(yc - yc_prev) <= 2:
					found_count = found_count + 1
				else:
					found_count = 0
		else:
			found_count = 0
		xc_prev = xc
		yc_prev = yc


    def execute(self, userdata):
        '''
        执行状态
        :param userdata:
        '''
		global sub, pub1, pub2, xc, yc, found_count
		# stop function
		sub.unregister()
		r1 = rospy.Rate(0.05)
		r2 = rospy.Rate(10)
		a = [0.0325,   -1.1880,   -0.0000,   -0.0002,    0.0004,  439]
		b = [-1.1016,  -0.0166,    0.0006,    0.0001,   -0.0003,  327]
		pos = position()
		# start pump
		pub2.publish(1)
		r2.sleep()
		# go forward
		pos.x = a[0] * xc + a[1] * yc + a[2] * xc * yc + a[3] * xc * xc + a[4] * yc * yc + a[5]
		pos.y = b[0] * xc + b[1] * yc + b[2] * xc * yc + b[3] * xc * xc + b[4] * yc * yc + b[5]
		pos.z = 20
		pub1.publish(pos)
		r2.sleep()
		# go down
		pos.z = -50
		pub1.publish(pos)
		r2.sleep()
		# go back home
		pos.x = 120
		pos.y = 0
		pos.z = 35
		pub1.publish(pos)
		r1.sleep()
        return 'succeeded'


class ReleaseObject(State):
    '''
    释放物体 功能
    '''
    def __init__(self):
        '''
        初始化
        '''
		global pub1, pub2
        State.__init__(self, outcomes=['succeeded', 'aborted'])
        self.task = 'release object' 
		rospy.init_node('image_converter', anonymous=True)
		pub1 = rospy.Publisher('position_write_topic', position, queue_size=10)
		pub2 = rospy.Publisher('pump_topic', status, queue_size=4)   
        
    def execute(self, userdata):        
        '''
        执行状态
        :param userdata:
        '''
		global pub1, pub2
		r1 = rospy.Rate(0.1)		# 5s
		r2 = rospy.Rate(10)			# 0.1s
		pos = position()
		# go forward
		pos.x = 200
		pos.y = 0
		pos.z = 0
		pub1.publish(pos)
		r1.sleep()
		# stop pump
		pub2.publish(0)
		r2.sleep()
		# go back home
		pos.x = 120
		pos.y = 0
		pos.z = 35
		pub1.publish(pos)
		r1.sleep()
        return 'succeeded'
            

# 获得厨房位置  
class GetLocation(State):
    '''
    生成导航位置
    '''
    def __init__(self):
        '''
        初始化
        '''
        State.__init__(self, outcomes=['succeeded', 'aborted'], output_keys=['waypoint_out'])     
        self.loc_pose = None;    
        
    def execute(self, userdata):
        '''
        状态执行函数
        :param userdata:
        '''
        self.loc_pose = self.get_pose()
        if self.loc_pose is None:
            return "aborted"
        userdata.waypoint_out = self.loc_pose
        return 'succeeded' 
    
    def get_pose(self):
        pose = None
        #to generate pose
         
        print pose        
        
        return self.split_str(pose)
    
    def split_str(self, str):
        
        loc_array = str.split(',')
        if len(loc_array) != 7:
            return None
        pose = Pose(Point(0, 0, 0), Quaternion(0.0, 0.0, 0.0, 1.0))
        
	pose.position.x = float(loc_array[0])
        pose.position.y = float(loc_array[1])
        pose.position.z = float(loc_array[2])
        pose.orientation.x = float(loc_array[3])
        pose.orientation.y = float(loc_array[4])
        pose.orientation.z = float(loc_array[5])
        pose.orientation.w = float(loc_array[6])
        
        return pose
    
class Nav2Waypoint(State):
    '''
    导航：巡航到指定的地点，通过move base
    '''
    def __init__(self):
        '''
        初始化
        '''
        State.__init__(self, outcomes=['succeeded', 'aborted'],
                       input_keys=['waypoint_in'])
        
        # Subscribe to the move_base action server        
        # self.move_base = actionlib.SimpleActionClient("move_base", MoveBaseAction)        
        # Wait up to 60 seconds for the action server to become available
        global move_base;
        move_base.wait_for_server(rospy.Duration(5))    
        
        rospy.loginfo("Connected to move_base action server")
        
        self.goal = MoveBaseGoal()
        self.goal.target_pose.header.frame_id = "/map"
    
        self.sayword_pub = rospy.Publisher("/xfsaywords", String, queue_size=1)

    def execute(self, userdata):
        '''
        状态执行函数
        :param userdata:用户数据
        '''
        self.goal.target_pose.pose = userdata.waypoint_in
        
        
        
        self.goal.target_pose.header.stamp = rospy.Time.now() 
        if self.goal.target_pose.pose is None:
            return 'aborted'
        # Send the goal pose to the MoveBaseAction server
        global move_base
        move_base.send_goal(self.goal)
        
        
        if self.preempt_requested():
            self.service_preempt()
            return 'preempted'
        rospy.loginfo('wait for result')
        
        global location_name
        self.sayword_pub.publish(loc_name2playword_ontheway[location_name]);
        
        # Allow 1 minute to get there
        finished_within_time = move_base.wait_for_result(rospy.Duration(60)) 

        # If the robot don't get there in time, abort the goal
        if not finished_within_time:
            move_base.cancel_goal()
            rospy.loginfo("Timed out achieving goal")
            return 'aborted'
        else:
            # We made it!
            state = move_base.get_state()
            if state == GoalStatus.SUCCEEDED:
                rospy.loginfo("Goal succeeded!")
            return 'succeeded'


class TurnBody(State):
    '''
    转动身体 功能
    '''
    def __init__(self):
        '''
        初始化
        '''
        State.__init__(self, outcomes=['succeeded', 'aborted'])
        self.task = 'turn body'        
        
    def execute(self, userdata):        
        '''
        执行状态
        :param userdata:
        '''
        return 'succeeded'    
    
class EndAbort(State):
    '''
    提示结果失败
    '''
    def __init__(self):
        '''
        初始化
        '''
        State.__init__(self, outcomes=['succeeded'])
        # self.play_sound  = PlaySound()
        self.task = 'end abort'        
    def execute(self, userdata):        
        '''
        执行状态
        :param userdata:
        '''
        return 'succeeded'        

class EndSuccess(State):
    '''
    提示结果成功
    '''
    def __init__(self):
        '''
        初始化
        '''
        State.__init__(self, outcomes=['succeeded'])
        # self.play_sound  = PlaySound()
        self.task = 'end success'        
    def execute(self, userdata):        
        '''
        执行状态
        :param userdata:
        '''
        self.sayword_pub.publish("任务完成");
        return 'succeeded'
        
                   
                
class CarryObject():
    '''
    场景：搬运物体
    功能：将目标运行到指定的位置
    '''
    def __init__(self):
        '''
        初始化
        '''
        rospy.init_node('s_carry_object_node', anonymous=False)
        
        rospy.on_shutdown(self.shutdown)
        self.switch_status = 0;
        self.sm_carry_object = None
        self.thr = None
        self.init_service_and_topic()
        # 控制
        self.stopworld = "停止处理"
        self.loaction_name = None
          
        
    def scene_status_swith_cb(self, req):
        '''
        场景状态切换回调函数，用于启动场景或者关闭场景
        :param req:请求参数
        '''
        print "-----------req status:%d" % req.END
        return_flag = -1
        if req.type == req.END:
             self.switch_status = 0
             global move_base
             move_base.cancel_goal()                
             for i in range(10):
                 self.cmd_vel_pub.publish(Twist())
                 
             if not self.thr is None:
                 try:
                     self.terminate_thread(self.thr)
                 except e:
                     pass  
                      
             return_flag = 0       
        if req.type == req.RUN:
             if self.switch_status == 0:
                 global location_name
                 location_name = req.param
                 print location_name
                 # thread.start_new_thread(self.timer, (1,1)) 
                 self.thr = threading.Thread(target=self.timer, args=(1, 1))
                 self.thr.start()
                 self.switch_status = 1
             return_flag = 1
         
        # self.master_s_pub.publish("",0)
        rospy.loginfo("req infomaion, type:%s,param:%s" % (req.type, req.param))
        print "s_carry_object status:%d" % return_flag
        return sceneResponse(return_flag) 
    
    def timer(self, no, interval):
        '''
        计时器
        :param no:
        :param interval:计时器间隔
        '''
        # time.sleep(interval);
        rospy.loginfo("req infomaion, status:%s" % (self.switch_status))
        if self.switch_status == 1:
            rospy.loginfo("starting to sm")
            self.build_state_machine();
            self.execute_sm()
        
        self.switch_status = 0
        rospy.loginfo("stopped to sm")
        thread.exit_thread() 


    def terminate_thread(self, thread):
        """
        Terminates a python thread from another thread.
        中止结束线程
        :param thread: a threading.Thread instance
        """
        try:
            if not thread.isAlive():
                return
    
            exc = ctypes.py_object(SystemExit)
            res = ctypes.pythonapi.PyThreadState_SetAsyncExc(
                ctypes.c_long(thread.ident), exc)
            if res == 0:
                raise ValueError("nonexistent thread id")
            elif res > 1:
                # """if it returns a number greater than one, you're in trouble,
                # and you should call it again with exc=NULL to revert the effect"""
                ctypes.pythonapi.PyThreadState_SetAsyncExc(thread.ident, None)
                raise SystemError("PyThreadState_SetAsyncExc failed")
        except e:
            pass
        self.cmd_vel_pub.publish(Twist())
    
    def init_service_and_topic(self):
        '''
        初始化服务和话题
        '''
        self.switch_status_service = rospy.Service('/s_carry_object', scene, self.scene_status_swith_cb)
        self.cmd_vel_pub = rospy.Publisher('/cmd_vel', Twist, queue_size=1)  
         
    def build_state_machine(self): 
        '''
        建立状态机
        '''
        if not self.sm_carry_object is None:
            self.sm_carry_object = None
        self.sm_carry_object = StateMachine(outcomes=['succeeded', 'aborted', 'preempted'])
        with self.sm_carry_object:
            StateMachine.add('GRASP_OBJECT', SpeaktoTipStart(), transitions={'succeeded':'GET_LOCATION',
                                                                               'aborted':'END_ABORT'})
            StateMachine.add('GET_LOCATION', GetLocation(), transitions={'succeeded':'NAV_TO_WAYPOINT',
                                                                               'aborted':'END_ABORT'},
                             remapping={'waypoint_out':'nav_waypoint'})
            StateMachine.add('NAV_TO_WAYPOINT', Nav2Waypoint(), transitions={'succeeded':'RELEASE_OBJECT',
                                                                               'aborted':'END_ABORT'},
                             remapping={'waypoint_in':'nav_waypoint'}) 
            StateMachine.add('RELEASE_OBJECT', SpeaktoTipStart(), transitions={'succeeded':'GET_LOCATION',
                                                                               'aborted':'END_ABORT'})
            StateMachine.add('TURN_BODY', TurnBody(), transitions={'succeeded':'GRASP_OBJECT',
                                                                               'aborted':'END_ABORT'})
            StateMachine.add('END_ABORT', EndSpeaktoTipAbort(), transitions={'succeeded':'succeeded'}) 
            StateMachine.add('END_SUCESS', EndSpeaktoTipSucess(), transitions={'succeeded':'succeeded'}) 
    def stop_cb(self, msg):
        '''
        停止回调函数
        :param msg:
        '''
        # rospy.loginfo("停止指令："+msg.data)
        print msg.data
        if msg.data == self.stopworld:
            switch_client = rospy.ServiceProxy('s_carry_object', scene)
            type = 0
            param = ""
            respon = switch_client(type, param)

            
    def execute_sm(self):   
        '''
        运行状态即机
        '''
        intro_server = IntrospectionServer('sm_carry_object', self.sm_carry_object, '/SM_ROOT')
        intro_server.start() 
        # Execute the state machine
        sm_outcome = self.sm_carry_object.execute()        
        rospy.loginfo('State Machine Outcome: ' + str(sm_outcome))
        intro_server.stop()
          
    def shutdown(self):
        '''
        关闭状态机
        '''
        rospy.loginfo("Stopping carry object")            
        rospy.sleep(1)
        self.cmd_vel_pub.publish(Twist())
        # rospy.spin()

if __name__ == '__main__':
    try:
        rospy.loginfo("Init carry object")   
        CarryObject()
        rospy.spin()
    except rospy.ROSInterruptException:
        rospy.loginfo("Finised  carry object")

