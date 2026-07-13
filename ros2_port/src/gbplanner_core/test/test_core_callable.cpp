// M3 acceptance test (task book §7-M3): the ROS-free gbplanner core builds
// under ament_cmake, includes no ros/ros.h, and is callable from a plain
// unit test — graph building, Dijkstra, GBP1 persistence, the pshim param
// registry, and Rrg construction with injected (null) map + IO.
#include <gtest/gtest.h>

#include <cstdio>
#include <string>
#include <vector>

#include "gbplanner_core/rrg.h"
#include "planner_common/graph_manager.h"
#include "planner_common/port/param.h"

TEST(GraphManagerTest, BuildQueryAndDijkstra) {
  GraphManager gm;
  StateVec s0(0, 0, 0, 0), s1(1, 0, 0, 0), s2(1, 1, 0, 0), s3(5, 5, 0, 0);
  Vertex* v0 = new Vertex(gm.generateVertexID(), s0);
  Vertex* v1 = new Vertex(gm.generateVertexID(), s1);
  Vertex* v2 = new Vertex(gm.generateVertexID(), s2);
  Vertex* v3 = new Vertex(gm.generateVertexID(), s3);
  gm.addVertex(v0);
  gm.addVertex(v1);
  gm.addVertex(v2);
  gm.addVertex(v3);
  gm.addEdge(v1, v0, 1.0);
  gm.addEdge(v2, v1, 1.0);
  gm.addEdge(v3, v2, 5.7);
  EXPECT_EQ(gm.getNumVertices(), 4);
  EXPECT_EQ(gm.getNumEdges(), 3);

  ShortestPathsReport rep;
  ASSERT_TRUE(gm.findShortestPaths(rep));
  std::vector<int> path;
  gm.getShortestPath(v3->id, rep, true, path);
  ASSERT_EQ(path.size(), 4u);  // 0 -> 1 -> 2 -> 3
  EXPECT_EQ(path.front(), v0->id);
  EXPECT_EQ(path.back(), v3->id);
}

TEST(GraphManagerTest, Gbp1PersistenceRoundtrip) {
  GraphManager gm;
  StateVec s0(0, 0, 0, 0), s1(2, 3, 1, 0);
  Vertex* v0 = new Vertex(gm.generateVertexID(), s0);
  Vertex* v1 = new Vertex(gm.generateVertexID(), s1);
  gm.addVertex(v0);
  gm.addVertex(v1);
  gm.addEdge(v1, v0, 3.74);

  const std::string path = "/tmp/gbp_core_test_graph.gbp1";
  gm.saveGraph(path);

  GraphManager gm2;
  gm2.loadGraph(path);
  EXPECT_EQ(gm2.getNumVertices(), gm.getNumVertices());
  EXPECT_EQ(gm2.getNumEdges(), gm.getNumEdges());
  ASSERT_NE(gm2.getVertex(v1->id), nullptr);
  EXPECT_NEAR(gm2.getVertex(v1->id)->state[1], 3.0, 1e-9);
  std::remove(path.c_str());
}

TEST(PshimParamTest, RegistryRoundtrip) {
  pshim::param::clear();
  pshim::param::set<double>("/gbplanner_node/RobotParams/size_x", 0.6);
  pshim::param::set<std::string>("/gbplanner_node/frame", "map");
  double d = 0.0;
  std::string s;
  EXPECT_TRUE(pshim::param::get("/gbplanner_node/RobotParams/size_x", d));
  EXPECT_DOUBLE_EQ(d, 0.6);
  EXPECT_TRUE(pshim::param::get("/gbplanner_node/frame", s));
  EXPECT_EQ(s, "map");
  EXPECT_FALSE(pshim::param::get("/nope", d));
  int wrong_type = 0;
  EXPECT_FALSE(pshim::param::get("/gbplanner_node/frame", wrong_type));
}

TEST(RrgTest, ConstructsHeadlessWithInjectedIO) {
  explorer::Rrg rrg(nullptr);  // map-free: unit test has no voxblox server
  int free_cloud_count = 0;
  pshim::RrgIO io;
  io.publish_free_cloud = [&free_cloud_count](
                              const sensor_msgs::msg::PointCloud2&) {
    ++free_cloud_count;
  };
  io.lookup_transform = [](const std::string&, const std::string&,
                           tf2::Transform* out) {
    out->setIdentity();
    return true;
  };
  rrg.setIO(io);
  // Side-effect-light public calls prove the object is alive and callable.
  rrg.setGlobalFrame("map");
  rrg.setBoundMode(BoundModeType::kExtendedBound);
}

int main(int argc, char** argv) {
  ::testing::InitGoogleTest(&argc, argv);
  return RUN_ALL_TESTS();
}
